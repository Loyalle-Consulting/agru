from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    agrusa_seller_employee_id = fields.Many2one(
        'hr.employee', string='Vendedor', index=True,
        domain="[('active', '=', True)]",
        help='Empleado comercial responsable, tenga o no acceso a Odoo.',
    )

    @api.onchange('agrusa_seller_employee_id')
    def _onchange_agrusa_seller_employee(self):
        for partner in self:
            if partner.agrusa_seller_employee_id:
                partner.user_id = partner.agrusa_seller_employee_id.user_id or False
            else:
                partner.user_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('agrusa_seller_employee_id'):
                employee = self.env['hr.employee'].browse(vals['agrusa_seller_employee_id'])
                vals['user_id'] = employee.user_id.id or False
        return super().create(vals_list)

    def write(self, vals):
        if 'agrusa_seller_employee_id' in vals:
            vals = dict(vals)
            employee = self.env['hr.employee'].browse(vals['agrusa_seller_employee_id']) if vals['agrusa_seller_employee_id'] else False
            vals['user_id'] = employee.user_id.id if employee and employee.user_id else False
        return super().write(vals)
