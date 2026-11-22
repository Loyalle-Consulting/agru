from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_reset_to_draft(self):
        """
        Odoo 19 (Enterprise / Odoo.sh)
        - Permite restablecer una transferencia en estado 'Hecho' a 'Borrador' para correcciones internas.
        - NO utiliza acciones estándar (cancel/draft) porque pueden estar bloqueadas por reglas/validaciones.
        - Limpia cantidades hechas en las líneas de movimiento (qty_done/quantity según versión).
        - Fuerza estados de moves y picking a 'draft'.
        """

        for picking in self:
            if picking.state != "done":
                raise UserError(_("La transferencia debe estar en estado 'Hecho' para restablecerla."))

            # Desbloquear si aplica
            if "is_locked" in picking._fields and picking.is_locked:
                picking.sudo().write({"is_locked": False})

            # Reset de cantidades hechas en stock.move.line
            move_lines = picking.move_line_ids
            if move_lines:
                vals = {}

                # Compatibilidad Odoo 17–19
                if "quantity" in move_lines._fields:
                    vals["quantity"] = 0
                if "qty_done" in move_lines._fields:
                    vals["qty_done"] = 0

                if vals:
                    move_lines.sudo().write(vals)

            # Forzar estados de movimientos a borrador
            if "move_ids" in picking._fields and picking.move_ids:
                picking.move_ids.sudo().write({"state": "draft"})

            # Forzar estado del picking a borrador
            picking.sudo().write({"state": "draft"})

            picking.message_post(
                body=_("Transferencia restablecida a borrador manualmente (botón personalizado).")
            )

        # 🔴 Cambio necesario en Odoo 19:
        # No retornar True cuando se ejecuta como acción masiva
        return {
            "type": "ir.actions.act_window_close"
        }