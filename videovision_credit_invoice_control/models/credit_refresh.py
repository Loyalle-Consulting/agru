# -*- coding: utf-8 -*-
"""Reunión 19-nov-2026 (C2): el estado de crédito se recalcula con cada movimiento del cliente, no solo en la
revisión diaria: al confirmar un pedido, al registrar una factura, nota de crédito, cobro, comprobante o protesto,
y al deshacer una conciliación (pago anulado). Los pedidos de clientes que cayeron en mora o sobre la línea quedan
pendientes de aprobación; los pendientes de clientes que se pusieron al día se liberan."""
from odoo import models

REFRESH_CTX = 'vv_credit_refreshing'
SKIP_REFRESH_CTX = 'vv_skip_credit_refresh'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _vv_credit_refresh_orders(self, source=None):
        if self.env.context.get(REFRESH_CTX) or self.env.context.get(SKIP_REFRESH_CTX):
            return
        partners = self.commercial_partner_id.with_context(**{REFRESH_CTX: True})
        if not partners:
            return
        # Liberar: si está instalado el módulo de cobro inteligente se usa su liberación (avisa al vendedor).
        if hasattr(partners, '_vv_credit_release_pending'):
            partners._vv_credit_release_pending(source=source)
        # Retener: pedidos por facturar (no pendientes, no aprobados a mano) de clientes con problema de crédito.
        # _vv_credit_hold_if_needed libera además los pendientes cuyo cliente ya cumple.
        orders = self.env['sale.order'].sudo().with_context(**{REFRESH_CTX: True}).search([
            ('partner_id', 'child_of', partners.ids),
            ('state', '=', 'sale'),
            ('invoice_status', 'in', ('to invoice', 'no')),
            ('vv_credit_state', 'not in', ('approved', 'rejected')),
        ])
        for company in orders.company_id:
            orders.filtered(lambda o: o.company_id == company).with_company(company)._vv_credit_hold_if_needed()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        # Un pedido nuevo revisa también los otros pedidos del cliente
        self.filtered(lambda o: o.state == 'sale').partner_id._vv_credit_refresh_orders()
        return res


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        if not self.env.context.get(SKIP_REFRESH_CTX):
            partners = posted.line_ids.filtered(lambda l: l.account_type == 'asset_receivable').partner_id
            if partners:
                partners._vv_credit_refresh_orders()
        return posted


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def reconcile(self):
        # El pago se registra antes de conciliarse: al conciliar es cuando el cliente queda al día.
        partners = self.filtered(lambda l: l.account_type == 'asset_receivable').partner_id
        res = super().reconcile()
        if partners and not self.env.context.get(SKIP_REFRESH_CTX):
            partners._vv_credit_refresh_orders()
        return res

    def remove_move_reconcile(self):
        partners = self.filtered(lambda l: l.account_type == 'asset_receivable').partner_id
        res = super().remove_move_reconcile()
        if partners and not self.env.context.get(SKIP_REFRESH_CTX):
            partners._vv_credit_refresh_orders()
        return res
