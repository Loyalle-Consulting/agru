# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self, force_qty=False):
        # A requisition delivery cannot take free WH4 stock before its
        # dedicated incoming purchase movement has been linked.
        eligible = self.filtered(
            lambda move: not (
                move.sale_line_id
                and move.sale_line_id.agrusa_supply_origin == 'requisition'
                and not move.move_orig_ids
                and move.state not in ('done', 'cancel')
            )
        )
        if eligible:
            return super(StockMove, eligible)._action_assign(force_qty=force_qty)
        return self.env['stock.move']
