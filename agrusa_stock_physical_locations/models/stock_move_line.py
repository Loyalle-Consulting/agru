from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    agrusa_source_position_id = fields.Many2one(
        'agrusa.physical.position', string='Posicion fisica origen',
        ondelete='restrict', copy=False)
    agrusa_dest_position_id = fields.Many2one(
        'agrusa.physical.position', string='Posicion fisica destino',
        ondelete='restrict', copy=False)

    agrusa_position_qty_on_hand = fields.Float(
        string='Existencia fisica', compute='_compute_agrusa_position_stock',
        digits='Product Unit of Measure', readonly=True)
    agrusa_position_qty_free = fields.Float(
        string='Disponible no reservado', compute='_compute_agrusa_position_stock',
        digits='Product Unit of Measure', readonly=True)

    agrusa_source_position_allowed = fields.Boolean(compute='_compute_agrusa_position_allowed')
    agrusa_dest_position_allowed = fields.Boolean(compute='_compute_agrusa_position_allowed')

    @api.depends('location_id.usage', 'location_dest_id.usage')
    def _compute_agrusa_position_allowed(self):
        for line in self:
            line.agrusa_source_position_allowed = line.location_id.usage == 'internal'
            line.agrusa_dest_position_allowed = line.location_dest_id.usage == 'internal'

    @api.depends('product_id', 'location_id', 'location_dest_id',
                 'agrusa_source_position_id', 'agrusa_dest_position_id',
                 'picking_id.picking_type_id.code', 'move_id.picking_type_id.code')
    def _compute_agrusa_position_stock(self):
        Quant = self.env['stock.quant'].sudo()
        for line in self:
            line.agrusa_position_qty_on_hand = 0.0
            line.agrusa_position_qty_free = 0.0
            if not line.product_id:
                continue
            picking_type = line.picking_id.picking_type_id or line.move_id.picking_type_id
            code = picking_type.code
            # Receipts display the destination; deliveries and internal moves
            # display the source. Stock is always scoped to a single Odoo location.
            location = line.location_dest_id if code == 'incoming' else line.location_id
            position = (line.agrusa_dest_position_id if code == 'incoming'
                        else line.agrusa_source_position_id)
            if not position or not location or location.usage != 'internal':
                continue
            # Do not create locations as a side effect of a read/compute.
            wh = line._agrusa_warehouse_for_location(location)
            mapped = self.env['stock.location'].search([
                ('agrusa_physical_position_id', '=', position.id),
                ('agrusa_position_warehouse_id', '=', wh.id),
            ], limit=1)
            if not mapped:
                continue
            quants = Quant.search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', mapped.id),
                ('company_id', '=', wh.company_id.id),
            ])
            line.agrusa_position_qty_on_hand = sum(quants.mapped('quantity'))
            line.agrusa_position_qty_free = sum(
                q.quantity - q.reserved_quantity for q in quants)

    def _agrusa_warehouse_for_location(self, location):
        """Find the warehouse by its stock root, not by a global shared position."""
        if not location or location.usage != 'internal':
            return self.env['stock.warehouse']
        warehouses = self.env['stock.warehouse'].search([
            ('company_id', '=', location.company_id.id or self.env.company.id)
        ])
        matches = warehouses.filtered(
            lambda wh: wh.view_location_id and (
                location.id == wh.view_location_id.id or
                location.id in self.env['stock.location'].search([
                    ('id', 'child_of', wh.view_location_id.id)
                ]).ids
            )
        )
        if len(matches) != 1:
            raise UserError(_(
                'No se pudo identificar una unica bodega para la ubicacion %s.'
            ) % location.display_name)
        return matches

    def _agrusa_is_storage(self, location, warehouse):
        return bool(warehouse and location and self.env['stock.location'].search_count([
            ('id', '=', location.id), ('id', 'child_of', warehouse.lot_stock_id.id),
        ]))

    def _agrusa_position_location(self, position, base_location):
        wh = self._agrusa_warehouse_for_location(base_location)
        if not self._agrusa_is_storage(base_location, wh):
            return base_location
        return position.get_warehouse_location(wh)

    def _agrusa_preview_position(self, position, location):
        if not position or not location or location.usage != 'internal':
            return location
        wh = self._agrusa_warehouse_for_location(location)
        if not self._agrusa_is_storage(location, wh):
            return location
        return self.env['stock.location'].search([
            ('agrusa_physical_position_id', '=', position.id),
            ('agrusa_position_warehouse_id', '=', wh.id),
        ], limit=1) or location

    @api.onchange('agrusa_source_position_id')
    def _onchange_agrusa_source_position(self):
        for line in self:
            if line.location_id.usage != 'internal':
                line.agrusa_source_position_id = False
            else:
                line.location_id = line._agrusa_preview_position(
                    line.agrusa_source_position_id, line.location_id)

    @api.onchange('agrusa_dest_position_id')
    def _onchange_agrusa_dest_position(self):
        for line in self:
            if line.location_dest_id.usage != 'internal':
                line.agrusa_dest_position_id = False
            else:
                line.location_dest_id = line._agrusa_preview_position(
                    line.agrusa_dest_position_id, line.location_dest_id)

    @api.onchange('location_id')
    def _onchange_agrusa_source_location(self):
        for line in self:
            line.agrusa_source_position_id = line.location_id.agrusa_physical_position_id

    @api.onchange('location_dest_id')
    def _onchange_agrusa_dest_location(self):
        for line in self:
            line.agrusa_dest_position_id = line.location_dest_id.agrusa_physical_position_id

    def _agrusa_apply_position_vals(self, vals, base):
        vals = dict(vals)
        for position_field, location_field in (
            ('agrusa_source_position_id', 'location_id'),
            ('agrusa_dest_position_id', 'location_dest_id'),
        ):
            if position_field not in vals and location_field not in vals:
                continue
            location = self.env['stock.location'].browse(vals.get(location_field, base.get(location_field)))
            if location and location.usage != 'internal':
                vals[position_field] = False
                continue
            if position_field not in vals:
                vals[position_field] = location.agrusa_physical_position_id.id or False
                continue
            if not vals[position_field] or not location:
                continue
            position = self.env['agrusa.physical.position'].browse(vals[position_field]).exists()
            if not position or not position.active:
                raise ValidationError(_('Posicion fisica inexistente o inactiva.'))
            vals[location_field] = self._agrusa_position_location(position, location).id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._agrusa_apply_position_vals(vals, vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if not (set(vals) & {'agrusa_source_position_id', 'agrusa_dest_position_id', 'location_id', 'location_dest_id'}):
            return super().write(vals)
        for line in self:
            base = {'location_id': line.location_id.id,
                    'location_dest_id': line.location_dest_id.id}
            individual = line._agrusa_apply_position_vals(vals, base)
            super(StockMoveLine, line).write(individual)
        return True

    def _agrusa_check_positions(self):
        """Positions are optional; native Odoo validates inventory movements."""
        return True

    def _action_done(self):
        if not self.env.context.get('agrusa_skip_position_validation'):
            self._agrusa_check_positions()
        return super()._action_done()

    def _agrusa_lookup_direction(self):
        self.ensure_one()
        picking_type = self.picking_id.picking_type_id or self.move_id.picking_type_id
        if picking_type.code == 'incoming' or (
                self.location_id.usage != 'internal' and
                self.location_dest_id.usage == 'internal'):
            return 'destination'
        return 'source'

    def action_agrusa_consult_positions(self):
        self.ensure_one()
        if not self.id or not self.product_id:
            raise UserError(_('Guarde primero la linea de operacion con su producto.'))
        direction = self._agrusa_lookup_direction()
        consultation_only = self.state in ('done', 'cancel')
        base = self.location_dest_id if direction == 'destination' else self.location_id
        if base.usage != 'internal':
            raise UserError(_('La ubicacion consultada debe ser interna.'))
        warehouse = self._agrusa_warehouse_for_location(base)
        Quant = self.env['stock.quant'].sudo()
        grouped = Quant.read_group([
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', warehouse.company_id.id),
            ('location_id', 'child_of', warehouse.lot_stock_id.id),
            ('location_id.agrusa_physical_position_id', '!=', False),
            ('location_id.agrusa_position_warehouse_id', '=', warehouse.id),
        ], ['quantity:sum', 'reserved_quantity:sum'], ['location_id'], lazy=False)
        rows = []
        for group in grouped:
            location = self.env['stock.location'].browse(group['location_id'][0])
            quantity = group.get('quantity', 0.0)
            reserved = group.get('reserved_quantity', 0.0)
            rows.append((0, 0, {
                'position_id': location.agrusa_physical_position_id.id,
                'location_id': location.id,
                'qty_on_hand': quantity,
                'qty_reserved': reserved,
                'qty_free': quantity - reserved,
            }))
        # Include empty positions for every operation.
        positions = self.env['agrusa.physical.position'].search([('active', '=', True)])
        locations = self.env['stock.location'].search([
            ('agrusa_position_warehouse_id', '=', warehouse.id),
            ('location_id', '=', warehouse.lot_stock_id.id),
            ('usage', '=', 'internal'),
        ])
        mapped = {loc.agrusa_physical_position_id.id: loc.id for loc in locations}
        existing = {row[2]['position_id']: row[2] for row in rows}
        rows = [(0, 0, existing.get(pos.id) or {
            'position_id': pos.id,
            'location_id': mapped.get(pos.id, False),
            'qty_on_hand': 0.0, 'qty_reserved': 0.0, 'qty_free': 0.0,
        }) for pos in positions]
        wizard = self.env['agrusa.position.lookup'].create({
            'direction': direction,
            'move_line_id': self.id,
            'product_id': self.product_id.id,
            'warehouse_id': warehouse.id,
            'demand_qty': self.quantity,
            'position_line_ids': rows,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Consultar posiciones de destino') if direction == 'destination'
                    else _('Consultar posiciones disponibles'),
            'res_model': 'agrusa.position.lookup',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
