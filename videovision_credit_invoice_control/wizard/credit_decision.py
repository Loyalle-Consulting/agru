# -*- coding: utf-8 -*-
from odoo import api, fields, models


class VvCreditDecision(models.TransientModel):
    _inherit = 'vv.credit.decision'

    decision = fields.Selection(selection=[
        ('approve', 'Aprobar (autoriza a facturar el pedido)'),
        ('reject', 'Rechazar'),
    ])

    @api.depends('order_ids')
    def _compute_summary(self):
        for wiz in self:
            texts = []
            for partner in wiz.order_ids.partner_id.commercial_partner_id:
                orders = wiz.order_ids.filtered(lambda o: o.partner_id.commercial_partner_id == partner)
                amount = sum(o.vv_credit_pending_amount or o._vv_amount_to_invoice_company() for o in orders)
                snap = partner._vv_credit_snapshot(extra_amount=amount)
                texts.append("%s\n%s" % (partner.display_name, partner._vv_format_snapshot(snap)))
            wiz.summary = "\n\n".join(texts)
