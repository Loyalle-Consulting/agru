from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    agrusa_provision_reference = fields.Char(
        string='Referencia de provisión',
        related='order_id.agrusa_provision_reference',
        readonly=True,
        store=False,
        help='Referencia informativa de provisión de la orden de compra.',
    )
