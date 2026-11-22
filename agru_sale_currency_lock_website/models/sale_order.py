# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_website_target_currency(self):
        """Devuelve la moneda REAL de cobro para pedidos del sitio web —
        la que siempre debe usarse al pagar, sin importar con qué lista
        de precios (Default, VIP, cualquier otra) haya navegado o
        comprado el cliente.

        Se usa la moneda de la COMPAÑÍA (Ajustes → Empresas), que ya
        existe y ya está configurada en cualquier instancia de Odoo — no
        se inventa ningún parámetro nuevo. A propósito NO se usa
        website.currency_id, porque ese campo depende de la lista de
        precios activa en cada sesión (varía según qué lista esté usando
        cada cliente: Default, VIP, etc.), y acá se necesita un valor
        fijo que no cambie según quién esté navegando."""
        self.ensure_one()
        if not self.website_id:
            return self.env['res.currency']
        return self.company_id.currency_id

    def _agru_sync_website_currency(self, post_message=True):
        """Para pedidos de sitio web: la moneda de cotización SIEMPRE es
        la moneda real de la tienda. No hay vendedor en el checkout que
        pueda (ni deba) elegir otra cosa — se fuerza automáticamente en
        cada creación/actualización del carrito."""
        self.ensure_one()
        website_currency = self._get_website_target_currency()
        if not website_currency or not self._is_currency_editable():
            return False
        if self.total_currency_id != website_currency:
            self.with_context(_agru_skip_currency_sync=True).total_currency_id = website_currency
        self._sync_rate_for_currency(post_message=post_message)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        # Corre DESPUÉS de que el módulo base ya aplicó su lógica normal
        # de backoffice (que asume la moneda de la lista de precios); acá
        # se re-fuerza específicamente para pedidos que vienen del sitio.
        orders = super().create(vals_list)
        for order in orders:
            if not order._is_currency_editable():
                continue
            if order._get_website_target_currency():
                order._agru_sync_website_currency(post_message=True)
        return orders

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('_agru_skip_currency_sync'):
            return res
        if 'pricelist_id' in vals or 'website_id' in vals or 'partner_id' in vals:
            # El cliente cambió de lista de precios en el sitio web (ej.
            # inicia sesión y le aplican su lista preferencial en USD):
            # se re-fuerza la moneda real de la tienda y se recalculan
            # las líneas con la tasa correspondiente a la nueva lista.
            for order in self:
                if not order._is_currency_editable():
                    continue
                if order._get_website_target_currency():
                    order._agru_sync_website_currency(post_message=True)
        return res
