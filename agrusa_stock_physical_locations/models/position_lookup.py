from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AgrusaPositionLookup(models.TransientModel):
    _name = 'agrusa.position.lookup'
    _description = 'Consulta de existencias por posicion'

    move_line_id = fields.Many2one('stock.move.line', required=True, readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', readonly=True)
    demand_qty = fields.Float(string='Cantidad de la linea', readonly=True)
    position_line_ids = fields.One2many('agrusa.position.lookup.line', 'wizard_id', readonly=True)


class AgrusaPositionLookupLine(models.TransientModel):
    _name = 'agrusa.position.lookup.line'
    _description = 'Existencias de producto en posicion'
    _order = 'position_id'

    wizard_id = fields.Many2one('agrusa.position.lookup', required=True, ondelete='cascade')
    position_id = fields.Many2one('agrusa.physical.position', readonly=True)
    location_id = fields.Many2one('stock.location', readonly=True)
    qty_on_hand = fields.Float(string='Existencia fisica', digits='Product Unit of Measure', readonly=True)
    qty_reserved = fields.Float(string='Reservado total', digits='Product Unit of Measure', readonly=True)
    qty_free = fields.Float(string='No reservado', digits='Product Unit of Measure', readonly=True)

    def action_select_position(self):
        self.ensure_one()
        move_line = self.wizard_id.move_line_id.exists()
        if not move_line or move_line.state in ('done', 'cancel'):
            raise UserError(_('La operacion ya no permite modificar su posicion.'))
        if not self.location_id or not self.position_id:
            raise UserError(_('Posicion sin ubicacion valida.'))
        if move_line.product_id != self.wizard_id.product_id:
            raise UserError(_('El producto de la operacion ha cambiado.'))
        wh = move_line._agrusa_warehouse_for_location(move_line.location_id)
        if wh != self.wizard_id.warehouse_id or self.location_id.agrusa_position_warehouse_id != wh:
            raise UserError(_('La bodega de origen ya no coincide. Actualice la consulta.'))
        if move_line.quantity > self.qty_on_hand:
            raise UserError(_('La cantidad supera la existencia fisica de esta posicion.'))
        # Respect Odoo's reservation checks; do not force, unreserve, or assign quants here.
        move_line.write({'agrusa_source_position_id': self.position_id.id})
        return {'type': 'ir.actions.act_window_close'}
