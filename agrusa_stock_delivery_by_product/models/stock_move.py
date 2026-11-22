from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    agrusa_sale_order_id = fields.Many2one(
        'sale.order', string='Orden de venta',
        related='sale_line_id.order_id', readonly=True,
    )
    agrusa_delivery_partner_id = fields.Many2one(
        'res.partner', string='Cliente',
        related='picking_id.partner_id', readonly=True,
    )
    agrusa_delivery_date_approx = fields.Date(
        string='Fecha entrega APROX',
        related='sale_line_id.agrusa_delivery_date_approx', readonly=True,
    )
    agrusa_import_purchase_line_id = fields.Many2one(
        'purchase.order.line', string='Línea OC importación',
        related='sale_line_id.agrusa_import_purchase_line_id', readonly=True,
    )
    agrusa_import_order_id = fields.Many2one(
        'purchase.order', string='OC importación',
        related='sale_line_id.agrusa_import_purchase_line_id.order_id', readonly=True,
    )
    agrusa_delivery_origin = fields.Selection(
        [('import', 'OC importación'), ('stock', 'Sin OC / Stock')],
        string='Origen abastecimiento',
        compute='_compute_agrusa_delivery_origin',
    )

    @api.depends('sale_line_id.agrusa_import_purchase_line_id')
    def _compute_agrusa_delivery_origin(self):
        for move in self:
            move.agrusa_delivery_origin = (
                'import' if move.agrusa_import_purchase_line_id else 'stock'
            )
