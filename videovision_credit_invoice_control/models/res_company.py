# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Reunión 05-nov: los pedidos no son deuda; el crédito utilizado son documentos emitidos.
    vv_credit_include_orders = fields.Boolean(default=False)
