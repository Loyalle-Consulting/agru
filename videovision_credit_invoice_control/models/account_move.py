# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError

from odoo.addons.videovision_credit_control.models.sale_order import BLOCK_REASONS, SKIP_CTX

CHECKED_CTX = 'vv_credit_post_checked'


class AccountMove(models.Model):
    _inherit = 'account.move'

    vv_credit_override_by = fields.Many2one(
        'res.users', string="Publicada sobre el crédito por", copy=False, readonly=True,
        help="Aprobador de crédito que publicó una factura sin pedido que no pasaba el control.")

    # ------------------------------------------------------------------
    # Evaluación
    # ------------------------------------------------------------------
    def _vv_credit_needs_check(self):
        self.ensure_one()
        return (
            self.move_type == 'out_invoice'
            and self.partner_id
            and not self.env.context.get(SKIP_CTX)
            and not self.env.context.get('install_mode')
        )

    def _vv_credit_orders(self):
        self.ensure_one()
        return self.sudo().invoice_line_ids.sale_line_ids.order_id.sudo(False)

    def _vv_credit_amount_for(self, orders):
        """Parte de la factura (moneda compañía, IVA incluido) que corresponde a `orders`."""
        self.ensure_one()
        total = abs(self.amount_total_signed)
        lines = self.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        all_base = sum(-l.balance for l in lines)
        part_base = sum(-l.balance for l in lines if l.sudo().sale_line_ids.order_id & orders)
        if not all_base or self.company_currency_id.compare_amounts(part_base, all_base) == 0:
            return total
        return self.company_currency_id.round(total * part_base / all_base)

    def _vv_credit_evaluate(self):
        """(motivo o False, foto o None, pedidos no cubiertos por una aprobación, monto evaluado)."""
        self.ensure_one()
        orders = self._vv_credit_orders()
        uncovered = orders.browse()
        if orders:
            applicable = orders.filtered(lambda o: o._vv_credit_applies())
            if not applicable:
                return False, None, uncovered, 0.0
            uncovered = applicable.filtered(lambda o: not o._vv_credit_approval_valid())
            if not uncovered:
                return False, None, uncovered, 0.0
            amount = self._vv_credit_amount_for(uncovered)
        else:
            amount = abs(self.amount_total_signed)
        reason, snap = self.partner_id._vv_credit_check_amount(amount, self.company_id)
        return reason, snap, uncovered, amount

    def _vv_credit_hold_orders(self, reason, snap, orders, amount):
        for order in orders:
            share = amount if len(orders) == 1 else self._vv_credit_amount_for(order)
            order._vv_set_credit_pending(reason, snap, amount=share)

    def _vv_credit_direct_error(self, reason, snap):
        detail = self.partner_id._vv_format_snapshot(snap)
        return _("No se puede publicar %(move)s: %(reason)s.\n\n%(detail)s\n\nSolo un aprobador de crédito "
                 "puede publicar una factura sin pedido que no pasa el control de crédito.",
                 move=self.display_name, reason=dict(BLOCK_REASONS)[reason].lower(), detail=detail)

    def _vv_credit_try_override(self, reason, snap):
        """Factura sin pedido: un aprobador puede publicarla dejando registro."""
        self.ensure_one()
        if not self.env.user.has_group('videovision_credit_control.group_vv_credit_approver'):
            raise UserError(self._vv_credit_direct_error(reason, snap))
        detail = self.partner_id._vv_format_snapshot(snap)
        self.vv_credit_override_by = self.env.user
        self.message_post(body=Markup("<b>%s</b><br/>%s") % (
            _("Publicada sobre el control de crédito (%(reason)s) por %(user)s",
              reason=dict(BLOCK_REASONS)[reason].lower(), user=self.env.user.name),
            Markup("<br/>").join(escape(l) for l in detail.split("\n"))))

    # ------------------------------------------------------------------
    # 1) Al crear la factura desde el pedido
    # ------------------------------------------------------------------
    def _vv_credit_screen_new_invoices(self):
        """Revisa las facturas recién creadas desde pedidos. Las que no pasan se eliminan (borrador) y sus
        pedidos quedan pendientes de aprobación. Devuelve (facturas que siguen, pedidos retenidos)."""
        kept = self.browse()
        blocked_orders = self.env['sale.order']
        for move in self:
            if not move._vv_credit_needs_check():
                kept |= move
                continue
            reason, snap, uncovered, amount = move._vv_credit_evaluate()
            if reason and uncovered:
                move._vv_credit_hold_orders(reason, snap, uncovered, amount)
                blocked_orders |= uncovered
                move.sudo().with_context(vv_skip_invoice_mirror=True).unlink()
                # Sección "Anticipos" que quedó vacía al eliminar la factura de anticipo.
                for order in uncovered:
                    dp_lines = order.order_line.filtered('is_downpayment')
                    if dp_lines and not dp_lines.filtered(lambda l: not l.display_type):
                        dp_lines.sudo().unlink()
            else:
                uncovered._vv_credit_clear_pending()
                kept |= move
        return kept, blocked_orders

    # ------------------------------------------------------------------
    # 2) Al publicar (borrador antiguo o cualquier otra vía)
    # ------------------------------------------------------------------
    def action_post(self):
        if self.env.context.get(SKIP_CTX) or self.env.context.get(CHECKED_CTX):
            return super().action_post()
        held = self.browse()
        blocked_orders = self.env['sale.order']
        for move in self.filtered(lambda m: m.state == 'draft' and m._vv_credit_needs_check()):
            reason, snap, uncovered, amount = move._vv_credit_evaluate()
            if not reason:
                uncovered._vv_credit_clear_pending()
                continue
            if uncovered:
                move._vv_credit_hold_orders(reason, snap, uncovered, amount)
                move.message_post(body=_("No se publicó: pedido(s) %s pendiente(s) de aprobación de crédito.",
                                         ", ".join(uncovered.mapped('name'))))
                blocked_orders |= uncovered
                held |= move
            else:
                move._vv_credit_try_override(reason, snap)
        rest = self - held
        res = super(AccountMove, rest.with_context(**{CHECKED_CTX: True})).action_post() if rest else False
        if held:
            return blocked_orders._vv_credit_blocked_notification(
                next_action={'type': 'ir.actions.client', 'tag': 'soft_reload'})
        return res

    def _post(self, soft=True):
        if not self.env.context.get(CHECKED_CTX) and not self.env.context.get(SKIP_CTX):
            for move in self.filtered(lambda m: m.state == 'draft' and m._vv_credit_needs_check()):
                reason, snap, uncovered, amount = move._vv_credit_evaluate()
                if not reason:
                    continue
                if uncovered:
                    raise UserError(_(
                        "No se puede publicar %(move)s: %(reason)s. El pedido %(orders)s requiere aprobación "
                        "de crédito (use \"Confirmar\" en la factura para dejarlo pendiente de aprobación).",
                        move=move.display_name, reason=dict(BLOCK_REASONS)[reason].lower(),
                        orders=", ".join(uncovered.mapped('name'))))
                move._vv_credit_try_override(reason, snap)
        return super()._post(soft=soft)
