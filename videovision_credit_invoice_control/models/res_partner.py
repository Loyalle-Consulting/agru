# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    vv_credit_is_manager = fields.Boolean(compute='_compute_vv_credit_is_manager')

    @api.depends_context('uid')
    def _compute_vv_credit_is_manager(self):
        value = self.env.user.has_group('videovision_credit_control.group_vv_credit_manager')
        for partner in self:
            partner.vv_credit_is_manager = value

    def _vv_credit_reason(self, snap):
        """Motivo de bloqueo para una foto de crédito (o False)."""
        policy = snap['policy']
        if policy == 'unrestricted':
            return False
        if policy == 'always':
            return 'always'
        if snap['is_overdue'] and snap['over_limit']:
            return 'both'
        if snap['is_overdue']:
            return 'overdue'
        if snap['over_limit']:
            return 'limit'
        return False

    def _vv_credit_check_amount(self, amount, company=None):
        """(motivo o False, foto) para facturar `amount` (moneda de la compañía) a este cliente."""
        self.ensure_one()
        partner = self.commercial_partner_id
        if company:
            partner = partner.with_company(company)
        snap = partner._vv_credit_snapshot(extra_amount=amount)
        return partner._vv_credit_reason(snap), snap

    def _vv_format_snapshot(self, snap):
        text = super()._vv_format_snapshot(snap)
        return text.replace("Este pedido:", "A facturar:")
