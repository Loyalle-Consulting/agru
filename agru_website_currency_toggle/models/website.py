# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.http import request


class Website(models.Model):
    _inherit = 'website'

    # Rutas donde el precio de línea que se ve en pantalla YA está forzado
    # a la moneda real de cobro (CLP) por agru_sale_currency_lock_website,
    # sin importar la lista de precios que originó ese producto. En estas
    # rutas el toggle tiene que partir SIEMPRE de CLP como base, o termina
    # convirtiendo dos veces un precio que ya estaba convertido.
    CART_LIKE_PATH_PREFIXES = ('/shop/cart',)

    def _agru_is_cart_like_route(self):
        if not request or not getattr(request, 'httprequest', None):
            return False
        path = request.httprequest.path or ''
        return any(path.startswith(p) for p in self.CART_LIKE_PATH_PREFIXES)

    def get_agru_secondary_currency(self):
        """CLP y USD son las dos monedas del toggle, siempre.

        Devuelve (displayed_currency, other_currency, rate):
        - displayed_currency: la moneda "principal" EFECTIVA para esta
          página en particular (ya considera el caso especial del
          carrito, ver más abajo). El template usa esto para el símbolo
          principal del toggle — antes lo recalculaba por su cuenta
          leyendo website.currency_id directo, lo que se desincronizaba
          del caso especial del carrito y hacía que ambos botones del
          toggle mostraran la misma moneda ahí.
        - other_currency: la moneda que compara el toggle (la "otra").
        - rate: tasa de displayed_currency -> other_currency.

        En la mayoría de las páginas displayed_currency sigue a la lista
        de precios activa (Público general -> CLP, Instaladores -> USD,
        etc.). PERO en el carrito (/shop/cart) el precio de cada línea ya
        viene forzado a CLP por agru_sale_currency_lock_website — ahí
        displayed_currency es SIEMPRE CLP, sin importar de qué lista vino
        el producto, o el toggle termina convirtiendo dos veces un monto
        que ya estaba en pesos.
        """
        self.ensure_one()
        Currency = self.env['res.currency']
        clp = Currency.search([('name', '=', 'CLP')], limit=1)
        usd = Currency.search([('name', '=', 'USD')], limit=1)
        if not clp or not usd:
            return False, False, 0.0

        if self._agru_is_cart_like_route():
            displayed_currency = clp
        else:
            displayed_currency = self.currency_id or self.company_id.currency_id

        if displayed_currency == usd:
            other_currency = clp
        else:
            displayed_currency = clp
            other_currency = usd

        company = self.company_id or self.env.company
        rate = displayed_currency._get_conversion_rate(
            displayed_currency, other_currency, company, fields.Date.context_today(self)
        )
        return displayed_currency, other_currency, rate
