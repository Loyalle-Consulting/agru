# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class AgrusaCreditAuthorization(models.Model):
    _name = 'agrusa.credit.authorization'
    _description = 'AGRUSA - Autorizacion de credito'
    _inherit = ['mail.thread']
    _order = 'id desc'

    sale_id = fields.Many2one('sale.order', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='sale_id.partner_id', store=True)
    company_id = fields.Many2one(related='sale_id.company_id', store=True)
    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    amount = fields.Monetary(required=True, readonly=True)
    currency_id = fields.Many2one(related='sale_id.currency_id')
    reason = fields.Text(required=True)
    decision_note = fields.Text()
    state = fields.Selection([('pending', 'Pendiente'), ('approved', 'Aprobada'),
                              ('rejected', 'Rechazada')], default='pending', tracking=True)

    def action_approve(self):
        if not self.env.user.has_group('agrusa_credit_control.group_credit_authorizer'):
            raise UserError(_('Solo un autorizador de credito puede aprobar.'))
        for request in self:
            if request.state != 'pending':
                raise UserError(_('Solo se pueden aprobar solicitudes pendientes.'))
            if request.sale_id.state not in ('draft', 'sent'):
                raise UserError(_('El pedido ya no esta en cotizacion.'))
            if float_compare(request.amount, request.sale_id.amount_total, precision_rounding=request.currency_id.rounding) != 0:
                raise UserError(_('El monto de la cotizacion cambio. Solicite nueva autorizacion.'))
            request.write({'state': 'approved', 'approved_by': self.env.user.id,
                           'approved_at': fields.Datetime.now()})
            request.sale_id.message_post(body=_('Credito aprobado excepcionalmente por %s.') % self.env.user.name)

    def action_reject(self):
        if not self.env.user.has_group('agrusa_credit_control.group_credit_authorizer'):
            raise UserError(_('Solo un autorizador de credito puede rechazar.'))
        for request in self:
            if request.state != 'pending':
                raise UserError(_('Solo se pueden rechazar solicitudes pendientes.'))
            request.state = 'rejected'
            request.sale_id.message_post(body=_('Solicitud de credito rechazada por %s.') % self.env.user.name)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    agrusa_credit_invoice_balance = fields.Monetary(
        string='Facturas pendientes AGRUSA', compute='_compute_agrusa_credit_panel',
        currency_field='agrusa_credit_currency_id')
    agrusa_credit_order_commitment = fields.Monetary(
        string='Pedidos pendientes de facturar', compute='_compute_agrusa_credit_panel',
        currency_field='agrusa_credit_currency_id')
    agrusa_credit_used = fields.Monetary(
        string='Credito utilizado AGRUSA', compute='_compute_agrusa_credit_panel',
        currency_field='agrusa_credit_currency_id')
    agrusa_credit_available = fields.Monetary(
        string='Credito disponible AGRUSA', compute='_compute_agrusa_credit_panel',
        currency_field='agrusa_credit_currency_id')
    agrusa_credit_overdue = fields.Monetary(
        string='Facturas vencidas AGRUSA', compute='_compute_agrusa_credit_panel',
        currency_field='agrusa_credit_currency_id')
    agrusa_credit_currency_id = fields.Many2one(
        'res.currency', compute='_compute_agrusa_credit_panel', string='Moneda credito AGRUSA')
    agrusa_credit_status = fields.Selection([
        ('no_limit', 'Sin limite configurado'),
        ('available', 'Disponible'),
        ('exceeded', 'Excedido'),
        ('overdue', 'Moroso'),
    ], compute='_compute_agrusa_credit_panel', string='Estado credito AGRUSA')

    def _agrusa_credit_balances(self, company):
        """Credit exposure in company currency; never count a posted invoice twice."""
        self.ensure_one()
        partner = self.commercial_partner_id
        today = fields.Date.context_today(self)
        Move = self.env['account.move'].sudo().with_company(company)
        invoices = Move.search([
            ('company_id', '=', company.id),
            ('commercial_partner_id', '=', partner.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ])
        debt = 0.0
        overdue = 0.0
        for inv in invoices:
            if inv.payment_state == 'reversed':
                continue
            residual = abs(inv.amount_residual_signed)
            sign = 1 if inv.move_type == 'out_invoice' else -1
            debt += sign * residual
            if (sign == 1 and inv.invoice_date_due and
                    inv.invoice_date_due < today and inv.amount_residual > 0):
                overdue += residual

        orders = self.env['sale.order'].sudo().with_company(company).search([
            ('company_id', '=', company.id),
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('state', 'in', ('sale', 'done')),
        ])
        commitment = 0.0
        for order in orders:
            # qty_invoiced tracks the portion already invoiced, including
            # partial invoices and reversals. Use gross line amount to include tax.
            pending = 0.0
            for line in order.order_line:
                if line.display_type or line.product_uom_qty <= 0:
                    continue
                posted_qty = 0.0
                for invoice_line in line.invoice_lines:
                    invoice = invoice_line.move_id
                    if invoice.state != 'posted' or invoice.move_type not in ('out_invoice', 'out_refund'):
                        continue
                    qty = invoice_line.product_uom_id._compute_quantity(
                        invoice_line.quantity, line.product_uom_id)
                    posted_qty += qty if invoice.move_type == 'out_invoice' else -qty
                remaining_qty = max(0.0, line.product_uom_qty - posted_qty)
                pending += line.price_total * remaining_qty / line.product_uom_qty
            commitment += order.currency_id._convert(
                pending, company.currency_id, company, today)
        return debt, commitment, overdue

    @api.depends_context('company')
    def _compute_agrusa_credit_panel(self):
        company = self.env.company
        for partner in self:
            commercial = partner.commercial_partner_id
            debt, committed, overdue = commercial._agrusa_credit_balances(company)
            used = debt + committed
            limit = commercial.credit_limit
            enabled = bool(company.account_use_credit_limit and commercial.use_partner_credit_limit)
            partner.agrusa_credit_currency_id = company.currency_id
            partner.agrusa_credit_invoice_balance = debt
            partner.agrusa_credit_order_commitment = committed
            partner.agrusa_credit_used = used
            partner.agrusa_credit_available = limit - used if enabled else 0.0
            partner.agrusa_credit_overdue = overdue
            partner.agrusa_credit_status = (
                'overdue' if overdue > 0 else
                'no_limit' if not enabled else
                'exceeded' if used > limit + company.currency_id.rounding else
                'available')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    agrusa_credit_authorization_ids = fields.One2many('agrusa.credit.authorization', 'sale_id')
    agrusa_credit_state = fields.Selection([('ok', 'Disponible'), ('blocked', 'Bloqueado'),
                                            ('approved', 'Autorizado')], compute='_compute_agrusa_credit_state')

    def _agrusa_credit_exposure(self):
        self.ensure_one()
        debt, commitment, overdue_amount = self.partner_id.commercial_partner_id._agrusa_credit_balances(self.company_id)
        return debt, commitment, overdue_amount > 0

    def _agrusa_credit_reason(self, extra=0.0):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        debt, committed, overdue = self._agrusa_credit_exposure()
        limit = partner.credit_limit
        enabled = bool(self.company_id.account_use_credit_limit and partner.use_partner_credit_limit)
        reasons = []
        if enabled and debt + committed + extra > limit + self.company_id.currency_id.rounding:
            reasons.append(_('Limite excedido: utilizado %(used).2f / cupo %(limit).2f') %
                           {'used': debt + committed + extra, 'limit': limit})
        if overdue:
            reasons.append(_('El cliente tiene facturas vencidas pendientes.'))
        return '\n'.join(reasons)

    def _agrusa_approved(self):
        self.ensure_one()
        return bool(self.agrusa_credit_authorization_ids.filtered(
            lambda a: a.state == 'approved' and
            float_compare(a.amount, self.amount_total, precision_rounding=self.currency_id.rounding) == 0))

    @api.depends('amount_total', 'partner_id', 'agrusa_credit_authorization_ids.state')
    def _compute_agrusa_credit_state(self):
        for order in self:
            reason = order._agrusa_credit_reason(extra=order.currency_id._convert(
                order.amount_total, order.company_id.currency_id, order.company_id,
                fields.Date.context_today(order))) if order.partner_id else ''
            order.agrusa_credit_state = 'approved' if reason and order._agrusa_approved() else ('blocked' if reason else 'ok')

    def action_agrusa_request_credit(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Solo puede solicitar credito para cotizaciones.'))
        extra = self.currency_id._convert(self.amount_total, self.company_id.currency_id,
                                          self.company_id, fields.Date.context_today(self))
        reason = self._agrusa_credit_reason(extra=extra)
        if not reason:
            raise UserError(_('La cotizacion no tiene bloqueo crediticio.'))
        req = self.env['agrusa.credit.authorization'].create({
            'sale_id': self.id, 'amount': self.amount_total, 'reason': reason})
        self.message_post(body=_('Solicitud de autorizacion de credito creada: %s') % req.display_name)
        return {'type': 'ir.actions.act_window', 'res_model': 'agrusa.credit.authorization',
                'res_id': req.id, 'view_mode': 'form', 'target': 'current'}

    def action_confirm(self):
        for order in self:
            if order.state not in ('draft', 'sent'):
                continue
            extra = order.currency_id._convert(order.amount_total, order.company_id.currency_id,
                                               order.company_id, fields.Date.context_today(order))
            reason = order._agrusa_credit_reason(extra=extra)
            if reason and not order._agrusa_approved():
                raise UserError(_('Confirmacion bloqueada por credito:\n%s\nSolicite autorizacion.') % reason)
        return super().action_confirm()


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        for move in self:
            if move.move_type != 'out_invoice' or move.state != 'draft':
                continue
            company = move.company_id
            partner = move.partner_id.commercial_partner_id
            if not partner:
                continue
            # A posted invoice replaces an existing sales commitment; do not charge twice.
            sales = move.invoice_line_ids.sale_line_ids.order_id
            if sales and all(s._agrusa_approved() or not s._agrusa_credit_reason() for s in sales):
                continue
            representative = self.env['sale.order'].sudo().search([
                ('company_id', '=', company.id),
                ('partner_id.commercial_partner_id', '=', partner.id)], limit=1)
            if not representative:
                # Direct invoices: enforce credit via accounting balances and limits.
                posted = self.env['account.move'].sudo().search([
                    ('company_id', '=', company.id), ('commercial_partner_id', '=', partner.id),
                    ('state', '=', 'posted'), ('move_type', 'in', ('out_invoice', 'out_refund'))])
                debt = sum((1 if m.move_type == 'out_invoice' else -1) * abs(m.amount_residual_signed)
                           for m in posted)
                overdue = any(m.move_type == 'out_invoice' and m.invoice_date_due and
                              m.invoice_date_due < fields.Date.context_today(move) and m.amount_residual > 0
                              for m in posted)
                if overdue or (company.account_use_credit_limit and partner.use_partner_credit_limit and
                    debt + abs(move.amount_total_signed) > partner.credit_limit):
                    raise UserError(_('Facturacion bloqueada: cliente moroso o sin cupo.'))
            else:
                extra = abs(move.amount_total_signed) if not sales else 0.0
                reason = representative._agrusa_credit_reason(extra=extra)
                if reason:
                    raise UserError(_('Facturacion bloqueada por credito:\n%s') % reason)
        return super()._post(soft=soft)
