from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    agrusa_invoice_address_ids = fields.Many2many(
        'res.partner', compute='_compute_agrusa_allowed_addresses',
        string='Direcciones de facturacion permitidas',
    )
    agrusa_delivery_address_ids = fields.Many2many(
        'res.partner', compute='_compute_agrusa_allowed_addresses',
        string='Direcciones de entrega permitidas',
    )

    @api.depends('partner_id', 'partner_id.commercial_partner_id')
    def _compute_agrusa_allowed_addresses(self):
        Partner = self.env['res.partner']
        for order in self:
            invoice = Partner.browse()
            delivery = Partner.browse()
            if order.partner_id:
                commercial = order.partner_id.commercial_partner_id
                # Incluye la empresa cliente y sus direcciones de tipo correcto,
                # incluso si estan vinculadas a un contacto de la misma empresa.
                invoice = commercial | Partner.search([
                    ('commercial_partner_id', '=', commercial.id),
                    ('type', '=', 'invoice'),
                ])
                delivery = commercial | Partner.search([
                    ('commercial_partner_id', '=', commercial.id),
                    ('type', '=', 'delivery'),
                ])
            order.agrusa_invoice_address_ids = invoice
            order.agrusa_delivery_address_ids = delivery
