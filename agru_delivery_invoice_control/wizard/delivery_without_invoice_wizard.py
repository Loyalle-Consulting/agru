from odoo import _, fields, models
from odoo.exceptions import UserError


class DeliveryWithoutInvoiceWizard(models.TransientModel):
    _name = "agru.delivery.without.invoice.wizard"
    _description = "Autorización de despacho sin factura"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Entrega",
        required=True,
        readonly=True,
    )
    reason = fields.Text(string="Motivo", required=True)

    def action_authorize(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "agru_delivery_invoice_control.group_authorize_delivery_without_invoice"
        ):
            raise UserError(_("No tiene permiso para autorizar despachos sin factura."))
        picking = self.picking_id
        if not picking._vv_requires_invoice_control():
            raise UserError(_("La entrega ya no se encuentra pendiente de validación."))
        if not picking._vv_get_invoice_coverage_issues():
            raise UserError(_("La entrega está completamente cubierta por facturas publicadas y no requiere autorización."))
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Debe indicar el motivo de la autorización."))
        picking.write({
            "vv_without_invoice_authorized": True,
            "vv_without_invoice_authorized_by_id": self.env.user.id,
            "vv_without_invoice_authorized_date": fields.Datetime.now(),
            "vv_without_invoice_reason": reason,
        })
        picking.message_post(
            body=_(
                "<b>Despacho sin factura autorizado</b><br/>"
                "Autorizado por: %(user)s<br/>Motivo: %(reason)s",
                user=self.env.user.display_name,
                reason=reason,
            )
        )
        return {"type": "ir.actions.act_window_close"}
