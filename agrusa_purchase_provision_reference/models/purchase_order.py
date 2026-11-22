from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    agrusa_provision_reference = fields.Char(
        string='Referencia de provisión',
        copy=True,
        help='Referencia informativa de la provisión de importación.',
    )
