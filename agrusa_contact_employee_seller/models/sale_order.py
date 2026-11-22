from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    agrusa_seller_employee_id = fields.Many2one(
        'hr.employee', string='Vendedor', index=True, copy=True,
        domain="[('active', '=', True)]",
        help='Vendedor comercial de esta operación, independiente de los permisos de acceso.',
    )

    @api.onchange('partner_id')
    def _onchange_agrusa_partner_employee(self):
        for order in self:
            if order.partner_id:
                order.agrusa_seller_employee_id = order.partner_id.commercial_partner_id.agrusa_seller_employee_id or order.partner_id.agrusa_seller_employee_id
                if order.agrusa_seller_employee_id.user_id:
                    order.user_id = order.agrusa_seller_employee_id.user_id

    @api.onchange('agrusa_seller_employee_id')
    def _onchange_agrusa_seller_employee(self):
        for order in self:
            if order.agrusa_seller_employee_id.user_id:
                order.user_id = order.agrusa_seller_employee_id.user_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            partner_id = vals.get('partner_id')
            if partner_id and 'agrusa_seller_employee_id' not in vals:
                partner = self.env['res.partner'].browse(partner_id)
                employee = partner.commercial_partner_id.agrusa_seller_employee_id or partner.agrusa_seller_employee_id
                vals['agrusa_seller_employee_id'] = employee.id or False
            employee_id = vals.get('agrusa_seller_employee_id')
            if employee_id:
                employee = self.env['hr.employee'].browse(employee_id)
                if employee.user_id:
                    vals['user_id'] = employee.user_id.id
        return super().create(vals_list)

    def write(self, vals):
        if 'agrusa_seller_employee_id' in vals and vals['agrusa_seller_employee_id']:
            employee = self.env['hr.employee'].browse(vals['agrusa_seller_employee_id'])
            if employee.user_id:
                vals = dict(vals, user_id=employee.user_id.id)
        return super().write(vals)
