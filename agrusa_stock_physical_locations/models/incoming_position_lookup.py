from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AgrusaIncomingPositionLookup(models.TransientModel):
    _name = 'agrusa.incoming.position.lookup'
    _description = 'Consulta informativa de posiciones en recepcion'

    move_line_id = fields.Many2one('stock.move.line', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', readonly=True)
    position_line_ids = fields.One2many(
        'agrusa.incoming.position.lookup.line', 'wizard_id', readonly=True)


class AgrusaIncomingPositionLookupLine(models.TransientModel):
    _name = 'agrusa.incoming.position.lookup.line'
    _description = 'Posicion de recepcion - consulta informativa'
    _order = 'position_id'

    wizard_id = fields.Many2one('agrusa.incoming.position.lookup', required=True, ondelete='cascade')
    position_id = fields.Many2one('agrusa.physical.position', readonly=True)
    location_id = fields.Many2one('stock.location', readonly=True)
    qty_on_hand = fields.Float(string='Existencia fisica', digits='Product Unit of Measure', readonly=True)
    qty_reserved = fields.Float(string='Reservado total', digits='Product Unit of Measure', readonly=True)
    qty_free = fields.Float(string='Disponible no reservado', digits='Product Unit of Measure', readonly=True)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def action_agrusa_consult_incoming_positions(self):
        self.ensure_one()
        if not self.id or not self.product_id:
            raise UserError(_('Guarde primero la linea de recepcion con su producto.'))
        picking_type = self.picking_id.picking_type_id or self.move_id.picking_type_id
        if picking_type.code != 'incoming':
            raise UserError(_('Esta consulta corresponde exclusivamente a recepciones.'))
        if not self.location_dest_id or self.location_dest_id.usage != 'internal':
            raise UserError(_('La ubicacion de destino no es una ubicacion interna.'))

        warehouse = self._agrusa_warehouse_for_location(self.location_dest_id)
        Position = self.env['agrusa.physical.position']
        Location = self.env['stock.location']
        Quant = self.env['stock.quant']
        positions = Position.search([('active', '=', True)])
        locations = Location.search([
            ('agrusa_position_warehouse_id', '=', warehouse.id),
            ('agrusa_physical_position_id', 'in', positions.ids),
            ('usage', '=', 'internal'),
        ])
        location_by_position = {
            loc.agrusa_physical_position_id.id: loc for loc in locations
        }
        totals_by_location = {}
        if locations:
            groups = Quant.read_group([
                ('product_id', '=', self.product_id.id),
                ('company_id', '=', warehouse.company_id.id),
                ('location_id', 'in', locations.ids),
            ], ['quantity:sum', 'reserved_quantity:sum'], ['location_id'], lazy=False)
            for group in groups:
                if group.get('location_id'):
                    totals_by_location[group['location_id'][0]] = (
                        group.get('quantity', 0.0), group.get('reserved_quantity', 0.0))
        rows = []
        for position in positions:
            loc = location_by_position.get(position.id)
            qty, reserved = totals_by_location.get(loc.id, (0.0, 0.0)) if loc else (0.0, 0.0)
            rows.append((0, 0, {
                'position_id': position.id,
                'location_id': loc.id if loc else False,
                'qty_on_hand': qty,
                'qty_reserved': reserved,
                'qty_free': qty - reserved,
            }))
        wizard = self.env['agrusa.incoming.position.lookup'].create({
            'move_line_id': self.id,
            'product_id': self.product_id.id,
            'warehouse_id': warehouse.id,
            'position_line_ids': rows,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consultar posiciones de destino'),
            'res_model': 'agrusa.incoming.position.lookup',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': self.env.ref('agrusa_stock_physical_locations.view_agrusa_incoming_position_lookup_form').id,
            'target': 'new',
        }
