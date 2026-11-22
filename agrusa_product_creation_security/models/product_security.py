from odoo import api, models, _
from odoo.exceptions import AccessError

GROUP = 'agrusa_product_creation_security.group_agrusa_product_creator'


def _check_product_creator(records):
    # sudo() is used by legitimate automated Odoo processes; do not block superuser.
    if records.env.su:
        return
    if not records.env.user.has_group(GROUP):
        raise AccessError(_(
            'AGRUSA: solo los usuarios del grupo "AGRUSA - Creacion de productos autorizada" '
            'pueden crear productos. Utilice el mantenedor de productos.'
        ))


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model_create_multi
    def create(self, vals_list):
        _check_product_creator(self)
        return super().create(vals_list)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model_create_multi
    def create(self, vals_list):
        _check_product_creator(self)
        return super().create(vals_list)
