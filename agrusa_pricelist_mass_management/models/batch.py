from odoo import api, fields, models

class AgrusaPriceBatch(models.Model):
    _name = 'agrusa.price.batch'
    _description = 'Historial de cambios masivos de tarifas AGRUSA'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(required=True, readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', required=True, readonly=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    applied_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    line_ids = fields.One2many('agrusa.price.batch.line', 'batch_id', readonly=True)
    change_count = fields.Integer(compute='_compute_count')

    @api.depends('line_ids')
    def _compute_count(self):
        for rec in self:
            rec.change_count = len(rec.line_ids)

class AgrusaPriceBatchLine(models.Model):
    _name = 'agrusa.price.batch.line'
    _description = 'Detalle historico de cambios de tarifa AGRUSA'
    _order = 'id'

    batch_id = fields.Many2one('agrusa.price.batch', required=True, ondelete='cascade', index=True)
    item_id = fields.Many2one('product.pricelist.item', string='Regla resultante', ondelete='set null')
    action = fields.Selection([('create','Creada'),('update','Actualizada')], required=True)
    description = fields.Char(required=True)
    before = fields.Text(string='Antes')
    after = fields.Text(string='Despues')
