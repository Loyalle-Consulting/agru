# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.videovision_credit_control.models.sale_order import BLOCK_REASONS, SKIP_CTX


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    vv_credit_state = fields.Selection(selection=[
        ('none', 'Sin revisión'),
        ('pending', 'Pendiente de aprobación'),
        ('approved', 'Aprobado manualmente'),
        ('auto', 'Aprobado (dentro de la política)'),
        ('rejected', 'Rechazado'),
    ])
    vv_credit_pending_amount = fields.Monetary(
        string="Monto a facturar retenido", currency_field='vv_company_currency_id', copy=False, readonly=True,
        help="Monto (moneda de la compañía) de la factura que se intentó emitir cuando quedó pendiente.")
    vv_company_currency_id = fields.Many2one(related='company_id.currency_id', string="Moneda compañía")
    vv_reserved_credit_issue = fields.Boolean(
        string="Reserva con problema de crédito", compute='_compute_vv_reserved_credit_issue',
        search='_search_vv_reserved_credit_issue',
        help="Pedido confirmado con stock reservado sin despachar cuyo cliente está moroso o sobre su línea.")

    # ------------------------------------------------------------------
    # Confirmar ya no revisa crédito (se revisa al facturar)
    # ------------------------------------------------------------------
    def action_confirm(self):
        res = super(SaleOrder, self.with_context(**{SKIP_CTX: True})).action_confirm()
        if not self.env.context.get(SKIP_CTX):
            # Reunión 12-nov: el pedido con problema de crédito queda "Pendiente de aprobación" al confirmar,
            # sin esperar a que alguien apriete "Crear factura". Confirma y reserva igual.
            self.filtered(lambda o: o.state == 'sale')._vv_credit_hold_if_needed()
        return res

    def _vv_credit_hold_if_needed(self):
        """Deja pendientes de aprobación los pedidos confirmados con algo por facturar cuyo cliente está moroso
        o sobre su línea. Libera los pendientes cuyo cliente ya cumple. Devuelve (retenidos, liberados)."""
        held = released = self.browse()
        for order in self:
            if order.state != 'sale' or not order._vv_credit_applies():
                continue
            if order.vv_credit_state in ('approved', 'rejected') or order._vv_credit_approval_valid():
                continue
            amount = order._vv_amount_to_invoice_company()
            if order.currency_id.is_zero(order.amount_to_invoice) and order.invoice_status != 'to invoice':
                continue
            reason, snap = order.partner_id._vv_credit_check_amount(amount, order.company_id)
            if reason and order.vv_credit_state != 'pending':
                order._vv_set_credit_pending(reason, snap, amount)
                held |= order
            elif not reason and order.vv_credit_state == 'pending':
                order._vv_credit_clear_pending()
                released |= order
        return held, released

    def action_vv_credit_pending_info(self):
        raise UserError(_("El pedido %s está pendiente de aprobación de crédito: un responsable debe aprobarlo "
                          "antes de facturar.", self[:1].name))

    @api.model
    def _vv_cron_credit_review(self):
        """Revisión diaria: pedidos confirmados por facturar cuyo cliente cayó en mora o sobre la línea pasan a
        pendientes de aprobación; los pendientes cuyo cliente ya está al día se liberan."""
        orders = self.search([('state', '=', 'sale'), ('invoice_status', 'in', ('to invoice', 'no')),
                              ('vv_credit_state', 'not in', ('approved', 'rejected'))])
        for company in orders.company_id:
            orders.filtered(lambda o: o.company_id == company).with_company(company)._vv_credit_hold_if_needed()

    # ------------------------------------------------------------------
    # Semáforo (solo aviso)
    # ------------------------------------------------------------------
    def _vv_amount_to_invoice_company(self):
        self.ensure_one()
        amount = self.amount_total if self.state in ('draft', 'sent') else self.amount_to_invoice
        return self.currency_id._convert(
            amount, self.company_id.currency_id, self.company_id,
            self.date_order or fields.Date.context_today(self))

    @api.depends('partner_id', 'amount_total', 'state', 'vv_credit_state', 'invoice_status')
    def _compute_vv_credit_alert(self):
        for order in self:
            order.vv_credit_alert = False
            order.vv_credit_preview_status = 'none'
            if not order.partner_id or not order._vv_credit_applies():
                continue
            if order.state not in ('draft', 'sent', 'sale') or order.vv_credit_state == 'pending':
                continue
            if order.state == 'sale' and order.invoice_status != 'to invoice' \
                    and order.currency_id.is_zero(order.amount_to_invoice):
                continue
            amount = order._vv_amount_to_invoice_company()
            reason, snap = order.partner_id._vv_credit_check_amount(amount, order.company_id)
            cur = snap['currency']
            parts = []
            if snap['policy'] == 'limit':
                parts.append(_("Línea %(limit)s · Utilizado %(used)s · Disponible %(avail)s",
                               limit=cur.format(snap['limit']), used=cur.format(snap['exposure']),
                               avail=cur.format(snap['limit'] - snap['exposure'])))
            elif snap['policy'] == 'cash':
                parts.append(_("Cliente contado (sin línea de crédito)"))
            elif snap['policy'] == 'unrestricted':
                parts.append(_("Cliente sin restricciones de crédito"))
            else:
                parts.append(_("Toda factura de este cliente requiere autorización"))
            if snap['overdue_amount']:
                parts.append(_("Vencido %(amount)s (%(days)s días)",
                               amount=cur.format(snap['overdue_amount']), days=snap['overdue_days']))
            if reason and not order._vv_credit_approval_valid():
                order.vv_credit_preview_status = 'warn'
                label = dict(BLOCK_REASONS)[reason]
                order.vv_credit_alert = Markup(
                    '<div class="alert alert-warning mb-0" role="alert"><i class="fa fa-exclamation-triangle me-1"/>'
                    '<strong>%s:</strong> %s. %s</div>') % (
                    _("Al facturar quedará %s", label.lower()), " · ".join(parts),
                    _("La factura requerirá aprobación de crédito; el pedido sí se puede confirmar y reservar."))
            else:
                order.vv_credit_preview_status = 'ok'
                order.vv_credit_alert = Markup(
                    '<div class="alert alert-success mb-0 py-1" role="status"><i class="fa fa-check-circle me-1"/>%s</div>'
                ) % " · ".join(parts)

    # ------------------------------------------------------------------
    # Retención al facturar
    # ------------------------------------------------------------------
    def _vv_set_credit_pending(self, reason, snap, amount=None):
        res = super()._vv_set_credit_pending(reason, snap)
        if amount is not None:
            self.vv_credit_pending_amount = amount
        return res

    def _vv_credit_clear_pending(self):
        """El cliente volvió a cumplir: se factura normal y se cierra la retención."""
        for order in self.filtered(lambda o: o.vv_credit_state == 'pending'):
            order.activity_unlink(['mail.mail_activity_data_todo'])
            order.write({'vv_credit_state': 'auto', 'vv_credit_block_reason': False, 'vv_credit_pending_amount': 0.0})
            order.message_post(body=_("Crédito OK al facturar: se libera la retención."))

    def _vv_credit_approve(self, note=False):
        """Aprobar autoriza a facturar el pedido completo (todas sus facturas) hasta su total actual."""
        self._vv_check_approver()
        for order in self.filtered(lambda o: o.vv_credit_state == 'pending'):
            amount = order._vv_amount_to_invoice_company() if order.state == 'sale' else order._vv_order_amount_company()
            reason, snap = order.partner_id._vv_credit_check_amount(amount, order.company_id)
            detail = order.partner_id._vv_format_snapshot(snap)
            order.write({
                'vv_credit_state': 'approved',
                'vv_credit_approved_by': self.env.user.id,
                'vv_credit_approved_date': fields.Datetime.now(),
                'vv_credit_approved_amount': order.amount_total,
                'vv_credit_decision_note': note,
            })
            order.message_post(body=Markup("<b>%s</b><br/>%s%s") % (
                _("Crédito aprobado por %(user)s para facturar hasta %(amount)s",
                  user=self.env.user.name, amount=order.currency_id.format(order.amount_total)),
                Markup("<br/>").join(escape(l) for l in detail.split("\n")),
                Markup("<br/><i>%s</i>") % note if note else "",
            ))
            order.activity_unlink(['mail.mail_activity_data_todo'])
            requester = order.vv_credit_requested_by or order.user_id
            if requester and requester != self.env.user:
                order.activity_schedule(
                    'mail.mail_activity_data_todo', user_id=requester.id,
                    summary=_("Crédito aprobado: ya puede facturar"),
                    note=note or _("Aprobado por %s", self.env.user.name))
            if order.state in ('draft', 'sent'):
                order.with_context(**{SKIP_CTX: True}).action_confirm()

    def write(self, vals):
        before = {}
        if 'order_line' in vals:
            before = {o.id: o._vv_credit_approval_valid() for o in self if o.state == 'sale'}
        res = super().write(vals)
        for order in self.filtered(lambda o: before.get(o.id) and not o._vv_credit_approval_valid()):
            order.message_post(body=_(
                "El total del pedido (%(total)s) supera el monto aprobado por crédito (%(approved)s): "
                "la próxima factura volverá a requerir aprobación.",
                total=order.currency_id.format(order.amount_total),
                approved=order.currency_id.format(order.vv_credit_approved_amount)))
        return res

    # ------------------------------------------------------------------
    # Reservas de clientes con problema de crédito
    # ------------------------------------------------------------------
    def _vv_reserved_orders_domain(self):
        return [('state', '=', 'sale'), ('picking_ids.state', '=', 'assigned'),
                ('picking_ids.picking_type_code', '=', 'outgoing')]

    def _vv_partners_with_credit_issue(self, partners):
        bad = self.env['res.partner']
        for partner in partners.commercial_partner_id:
            snap = partner.with_company(self.env.company)._vv_credit_snapshot()
            if snap['policy'] != 'unrestricted' and (snap['is_overdue'] or snap['over_limit']):
                bad |= partner
        return bad

    def _compute_vv_reserved_credit_issue(self):
        reserved = self.filtered_domain(self._vv_reserved_orders_domain())
        bad = self._vv_partners_with_credit_issue(reserved.partner_id)
        for order in self:
            order.vv_reserved_credit_issue = order in reserved and order.partner_id.commercial_partner_id in bad

    def _search_vv_reserved_credit_issue(self, operator, value):
        if operator in ('in', 'not in'):
            value = True in value
            operator = '=' if operator == 'in' else '!='
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise NotImplementedError()
        reserved = self.search(self._vv_reserved_orders_domain())
        bad = self._vv_partners_with_credit_issue(reserved.partner_id)
        ids = reserved.filtered(lambda o: o.partner_id.commercial_partner_id in bad).ids
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', ids)]


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def create_invoices(self):
        if self.env.context.get(SKIP_CTX):
            return super().create_invoices()
        self._check_amount_is_positive()
        invoices = self._create_invoices(self.sale_order_ids)
        kept, blocked_orders = invoices._vv_credit_screen_new_invoices()
        if not blocked_orders:
            return self.sale_order_ids.action_view_invoice(invoices=invoices)
        return blocked_orders._vv_credit_blocked_notification(
            next_action=self.sale_order_ids.action_view_invoice(invoices=kept) if kept
            else {'type': 'ir.actions.client', 'tag': 'soft_reload'})


class SaleOrderNotify(models.Model):
    _inherit = 'sale.order'

    def _vv_credit_blocked_notification(self, next_action=None):
        names = ", ".join(self.mapped('name'))
        reasons = ", ".join(sorted({dict(BLOCK_REASONS)[o.vv_credit_block_reason] for o in self if o.vv_credit_block_reason}))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Factura retenida por crédito"),
                'message': _("%(orders)s: %(reasons)s. No se emitió la factura; quedó pendiente de aprobación "
                             "de crédito (se avisó al responsable).", orders=names, reasons=reasons.lower()),
                'type': 'warning',
                'sticky': True,
                'next': next_action or {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
