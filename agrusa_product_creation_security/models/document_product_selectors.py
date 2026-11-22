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


class _ProductSelectorViewMixin:
    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type in ('form', 'list', 'kanban'):
            return _restrict_product_selectors(result)
        return result


class SaleOrder(_ProductSelectorViewMixin, models.Model):
    _inherit = 'sale.order'


class SaleOrderLine(_ProductSelectorViewMixin, models.Model):
    _inherit = 'sale.order.line'


class PurchaseOrder(_ProductSelectorViewMixin, models.Model):
    _inherit = 'purchase.order'


class PurchaseOrderLine(_ProductSelectorViewMixin, models.Model):
    _inherit = 'purchase.order.line'


class StockPicking(_ProductSelectorViewMixin, models.Model):
    _inherit = 'stock.picking'


class StockMove(_ProductSelectorViewMixin, models.Model):
    _inherit = 'stock.move'


class StockMoveLine(_ProductSelectorViewMixin, models.Model):
    _inherit = 'stock.move.line'


class AccountMove(_ProductSelectorViewMixin, models.Model):
    _inherit = 'account.move'


class AccountMoveLine(_ProductSelectorViewMixin, models.Model):
    _inherit = 'account.move.line'
