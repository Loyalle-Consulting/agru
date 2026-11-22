from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    agrusa_provision_reference = fields.Char(
        string='Referencia de provisión',
        related='purchase_id.agrusa_provision_reference',
        readonly=True,
        store=False,
        help='Referencia informativa de la orden de compra vinculada.',
    )
