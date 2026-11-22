# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def write(self, vals):
        result = super().write(vals)
        if 'date_order' in vals:
            for order in self:
                for line in order.order_line.filtered(lambda l: not l.display_type and not l.agrusa_delivery_date_manual):
                    expected = line._agrusa_expected_delivery_date()
                    if line.agrusa_delivery_date_approx != expected:
                        line.with_context(agrusa_skip_delivery_sync=True).write({
                            'agrusa_delivery_date_approx': expected,
                            'customer_lead': line._agrusa_days_to(expected),
                        })
        if 'date_order' in vals:
            self.order_line._agrusa_sync_stock_move_dates()
        return result

    def action_confirm(self):
        self.order_line._agrusa_validate_min_delivery_date()
        result = super().action_confirm()
        self.order_line._agrusa_sync_stock_move_dates()
        return result
