from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AgrusaPhysicalPosition(models.Model):
    _name = 'agrusa.physical.position'
    _description = 'AGRUSA Posicion fisica compartida'
    _order = 'aisle, rack, longitudinal, level, id'

    name = fields.Char(string='Codigo', compute='_compute_name', store=True)
    aisle = fields.Char(string='Pasillo', required=True)
    rack = fields.Char(string='Rack', required=True)
    longitudinal = fields.Char(string='Posicion longitudinal', required=True)
    level = fields.Char(string='Nivel / Altura', required=True)
    position_type = fields.Selection([('rack', 'Rack')], default='rack', required=True, string='Tipo')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Observaciones')
    location_ids = fields.One2many('stock.location', 'agrusa_physical_position_id', string='Ubicaciones por bodega', readonly=True)

    @api.depends('aisle', 'rack', 'longitudinal', 'level')
    def _compute_name(self):
        for rec in self:
            rec.name = 'P%s-R%s-L%s-N%s' % (rec.aisle or '', rec.rack or '', rec.longitudinal or '', rec.level or '')

    @api.constrains('aisle', 'rack', 'longitudinal', 'level')
    def _check_unique_position(self):
        for rec in self:
            if self.search_count([
                ('aisle', '=', rec.aisle), ('rack', '=', rec.rack),
                ('longitudinal', '=', rec.longitudinal), ('level', '=', rec.level),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(_('Esta posicion fisica ya existe.'))

    def get_warehouse_location(self, warehouse):
        self.ensure_one()
        if not self.active:
            raise UserError(_('La posicion %s esta inactiva.') % self.display_name)
        root = warehouse.lot_stock_id
        if not root:
            raise UserError(_('La bodega %s no tiene ubicacion de stock.') % warehouse.display_name)
        location = self.env['stock.location'].search([
            ('agrusa_physical_position_id', '=', self.id),
            ('agrusa_position_warehouse_id', '=', warehouse.id),
        ], limit=1)
        if not location:
            location = self.env['stock.location'].create({
                'name': self.name,
                'location_id': root.id,
                'usage': 'internal',
                'company_id': warehouse.company_id.id,
                'agrusa_physical_position_id': self.id,
                'agrusa_position_warehouse_id': warehouse.id,
            })
        return location


class StockLocation(models.Model):
    _inherit = 'stock.location'

    agrusa_physical_position_id = fields.Many2one('agrusa.physical.position', string='Posicion fisica', index=True, ondelete='restrict')
    agrusa_position_warehouse_id = fields.Many2one('stock.warehouse', string='Bodega de la posicion', index=True, ondelete='restrict')

    @api.constrains('agrusa_physical_position_id', 'agrusa_position_warehouse_id', 'location_id')
    def _check_position_mapping(self):
        for rec in self.filtered('agrusa_physical_position_id'):
            if not rec.agrusa_position_warehouse_id:
                raise ValidationError(_('Debe indicar la bodega Odoo para la posicion fisica.'))
            root = rec.agrusa_position_warehouse_id.lot_stock_id
            if rec.location_id != root:
                raise ValidationError(_('La posicion debe ser hija directa de la ubicacion Stock de su bodega.'))
            if self.search_count([
                ('agrusa_physical_position_id', '=', rec.agrusa_physical_position_id.id),
                ('agrusa_position_warehouse_id', '=', rec.agrusa_position_warehouse_id.id),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(_('Ya existe una ubicacion de esta posicion para la bodega indicada.'))
