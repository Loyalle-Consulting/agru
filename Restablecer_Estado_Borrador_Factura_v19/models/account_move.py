from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    x_from_editar_factura_reset = fields.Boolean(
        string="Reset to Draft (custom)",
        default=False,
        copy=False,
    )

    x_prev_l10n_cl_dte_status = fields.Selection(
        selection=lambda self: self._fields["l10n_cl_dte_status"].selection
        if "l10n_cl_dte_status" in self._fields else [],
        string="Previous DTE Status",
        copy=False,
        readonly=True,
    )

    # ---------------------------------------------------------
    # RESET PERSONALIZADO
    # ---------------------------------------------------------
    def action_editar_factura_reset_draft(self):

        allowed_types = ("out_invoice", "out_refund", "in_invoice", "in_refund")

        for move in self:

            if move.state != "posted":
                continue

            if move.move_type not in allowed_types:
                continue

            # Respaldar estado DTE si existe
            if "l10n_cl_dte_status" in move._fields:
                move.x_prev_l10n_cl_dte_status = move.l10n_cl_dte_status

            # Marcar como reset personalizado
            move.x_from_editar_factura_reset = True

            # ⚠️ IMPORTANTE:
            # NO usar button_cancel()
            # NO usar button_draft()
            # Evitamos validaciones de l10n_cl_edi

            move.sudo().write({
                "state": "draft",
            })

        return True

    # ---------------------------------------------------------
    # POST PERSONALIZADO
    # ---------------------------------------------------------
    def action_post(self):

        moves_flagged = self.filtered(lambda m: m.x_from_editar_factura_reset)
        moves_normal = self - moves_flagged

        result = True

        # Posteos normales
        if moves_normal:
            result = super(AccountMove, moves_normal).action_post()

        # Posteos de facturas restablecidas
        if moves_flagged:

            result_flagged = super(AccountMove, moves_flagged).action_post()

            # Forzar estado SII a accepted nuevamente
            if "l10n_cl_dte_status" in moves_flagged._fields:
                moves_flagged.sudo().write({
                    "l10n_cl_dte_status": "accepted"
                })

            # Limpiar marcador
            moves_flagged.sudo().write({
                "x_from_editar_factura_reset": False
            })

            result = result_flagged

        return result