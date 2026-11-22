# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    list_price_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda del precio base',
        default=lambda self: self.env.company.currency_id,
        help='En Odoo, el campo "Precio de venta" no tiene moneda propia: '
             'siempre se asume que está en la moneda de la compañía. Este '
             'campo permite declarar en qué moneda está EN REALIDAD ese '
             'precio (ej. si se cargó en dólares aunque el sistema lo '
             'trate como pesos). Se usa únicamente cuando un pedido cae '
             'de vuelta a este precio base por no tener una regla propia '
             'en la lista de precios usada — para convertirlo bien a la '
             'moneda de esa lista, en vez de asumir que ya está en la '
             'moneda correcta.',
    )
