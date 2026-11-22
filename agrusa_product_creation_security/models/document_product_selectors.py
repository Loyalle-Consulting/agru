import ast
from lxml import etree
from odoo import api, models

_PRODUCT_FIELDS = {'product_id', 'product_template_id', 'product_variant_id'}


def _restrict_product_selectors(result):
    """Apply restrictions to all product fields, including nested inline lists/forms.

    Executed after Odoo has assembled the final view. Does not change database views
    and does not affect the product maintenance screens.
    """
    arch = result.get('arch')
    if not arch:
        return result
    root = etree.fromstring(arch.encode('utf-8') if isinstance(arch, str) else arch)
    changed = False
    for node in root.iter('field'):
        if node.get('name') not in _PRODUCT_FIELDS:
            continue
        options = {}
        original = node.get('options')
        if original:
            try:
                parsed = ast.literal_eval(original)
                if isinstance(parsed, dict):
                    options = parsed
            except (ValueError, SyntaxError):
                # Preserve unparseable dynamic options instead of damaging them.
                # Standard product fields normally use literal option dictionaries.
                continue
        options.update({
            'no_create': True,
            'no_create_edit': True,
            'no_quick_create': True,
            'no_open': True,
        })
        node.set('options', repr(options))
        node.set('can_create', 'false')
        changed = True
    if changed:
        result = dict(result)
        result['arch'] = etree.tostring(root, encoding='unicode')
    return result




class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result
