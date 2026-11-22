# -*- coding: utf-8 -*-
from odoo import models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def write(self, vals):
        before = {line.id: line.date_planned for line in self} if 'date_planned' in vals else {}
        result = super().write(vals)
        if before and not self.env.context.get('agrusa_skip_delivery_sync'):
            changed = self.filtered(lambda line: before[line.id] != line.date_planned)
            if changed:
                sale_lines = self.env['sale.order.line'].sudo().search([
                    ('agrusa_import_purchase_line_id', 'in', changed.ids),
                    ('order_id.state', 'in', ['draft', 'sent', 'sale', 'done']),
                    ('agrusa_delivery_date_manual', '=', False),
                ])
                for line in sale_lines:
                    target = line._agrusa_expected_delivery_date()
                    if target:
                        line.with_context(agrusa_skip_delivery_sync=True).write({
                            'customer_lead': line._agrusa_days_to(target),
                            'agrusa_delivery_date_approx': target,
                        })
                        line._agrusa_sync_stock_move_dates()
        return result
