from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Check only actual processed move lines. The standard Odoo flow still
        # owns reservations, backorders, lot tracking and done quantities.
        for picking in self:
            picking.move_line_ids._agrusa_check_positions()
        return super().button_validate()
