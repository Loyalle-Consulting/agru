from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    agrusa_default_import_factor = fields.Float(
        string='Factor comercial predeterminado', digits=(16, 6), default=0.0,
        help='Factor sugerido para nuevas lineas de compra de importacion. '
             'Cero utiliza el factor general de la orden de compra.')

    @api.constrains('agrusa_default_import_factor')
    def _check_agrusa_default_import_factor(self):
        for product in self:
            if product.agrusa_default_import_factor < 0:
                raise ValidationError(_('El factor predeterminado no puede ser negativo.'))
