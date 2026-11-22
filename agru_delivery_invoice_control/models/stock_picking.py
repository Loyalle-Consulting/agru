from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = "stock.picking"

    vv_manual_invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura de venta asociada",
        copy=False,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), "
               "('company_id', '=', company_id)]",
        help="Úsela en entregas creadas directamente desde Inventario. En entregas "
             "originadas por un pedido de venta, la factura se detecta automáticamente.",
    )
    vv_has_posted_invoice = fields.Boolean(
        string="Tiene factura publicada",
        compute="_compute_vv_invoice_control",
    )
    vv_invoice_coverage_ok = fields.Boolean(
        string="Cantidades cubiertas por factura",
        compute="_compute_vv_invoice_control",
        help="Indica si la cantidad que se intenta entregar está completamente "
             "cubierta por facturas de cliente publicadas.",
    )
    vv_posted_invoice_ids = fields.Many2many(
        comodel_name="account.move",
        string="Facturas publicadas detectadas",
        compute="_compute_vv_invoice_control",
    )
    vv_without_invoice_authorized = fields.Boolean(
        string="Despacho sin factura autorizado",
        copy=False,
        readonly=True,
        tracking=True,
    )
    vv_without_invoice_authorized_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Autorizado por",
        copy=False,
        readonly=True,
        tracking=True,
    )
    vv_without_invoice_authorized_date = fields.Datetime(
        string="Fecha de autorización",
        copy=False,
        readonly=True,
        tracking=True,
    )
    vv_without_invoice_reason = fields.Text(
        string="Motivo de autorización",
        copy=False,
        readonly=True,
        tracking=True,
    )

    def _vv_sale_orders(self):
        """Return every sale order linked to the picking or its stock moves."""
        self.ensure_one()
        orders = self.env["sale.order"]
        if "sale_id" in self._fields:
            orders |= self.sale_id
        sale_lines = self.move_ids.filtered("sale_line_id").mapped("sale_line_id")
        return orders | sale_lines.mapped("order_id")

    def _vv_get_posted_invoices(self):
        self.ensure_one()
        invoices = self.env["account.move"]
        if self.vv_manual_invoice_id:
            invoices |= self.vv_manual_invoice_id
        invoices |= self._vv_sale_orders().mapped("invoice_ids")
        return invoices.filtered(
            lambda move: move.move_type == "out_invoice"
            and move.state == "posted"
            and move.company_id == self.company_id
            and move.payment_state != "reversed"
        )

    @api.depends(
        "vv_manual_invoice_id",
        "vv_manual_invoice_id.state",
        "vv_manual_invoice_id.payment_state",
        "vv_manual_invoice_id.invoice_line_ids.quantity",
        "move_ids.sale_line_id.order_id.invoice_ids.state",
        "move_ids.sale_line_id.order_id.invoice_ids.payment_state",
        "move_ids.quantity",
        "move_ids.product_uom_qty",
        "move_ids.state",
        "move_ids.sale_line_id.qty_delivered",
        "move_ids.sale_line_id.invoice_lines.quantity",
        "move_ids.sale_line_id.invoice_lines.move_id.state",
        "move_ids.sale_line_id.invoice_lines.move_id.move_type",
        "move_ids.sale_line_id.invoice_lines.move_id.payment_state",
    )
    def _compute_vv_invoice_control(self):
        for picking in self:
            invoices = picking._vv_get_posted_invoices()
            picking.vv_posted_invoice_ids = invoices
            picking.vv_has_posted_invoice = bool(invoices)
            picking.vv_invoice_coverage_ok = (
                not picking._vv_requires_invoice_control()
                or not picking._vv_get_invoice_coverage_issues()
            )

    @api.constrains("vv_manual_invoice_id", "partner_id", "company_id")
    def _check_vv_manual_invoice(self):
        for picking in self.filtered("vv_manual_invoice_id"):
            invoice = picking.vv_manual_invoice_id
            if (
                invoice.move_type != "out_invoice"
                or invoice.state != "posted"
                or invoice.payment_state == "reversed"
            ):
                raise ValidationError(_("La factura asociada debe ser una factura de cliente publicada."))
            if invoice.company_id != picking.company_id:
                raise ValidationError(_("La factura asociada debe pertenecer a la misma empresa de la entrega."))
            if (
                picking.partner_id
                and invoice.commercial_partner_id != picking.partner_id.commercial_partner_id
            ):
                raise ValidationError(_("La factura asociada debe pertenecer al mismo cliente de la entrega."))

    def _vv_requires_invoice_control(self):
        self.ensure_one()
        return self.picking_type_id.code == "outgoing" and self.state not in ("done", "cancel")

    def _vv_move_quantity(self, move):
        """Quantity that Odoo is about to validate, expressed in move UoM."""
        self.ensure_one()
        if "quantity" in move._fields:
            return move.quantity
        # Compatibility fallback. Odoo 19 normally uses ``quantity``.
        return sum(move.move_line_ids.mapped("quantity"))

    def _vv_sale_line_current_quantities(self):
        """Quantities in this picking, grouped and expressed in sale-line UoM."""
        self.ensure_one()
        quantities = defaultdict(float)
        component_equivalent_quantities = defaultdict(float)
        for move in self.move_ids.filtered(lambda m: m.state != "cancel" and m.sale_line_id):
            quantity = self._vv_move_quantity(move)
            if float_is_zero(quantity, precision_rounding=move.product_uom.rounding):
                continue
            sale_line = move.sale_line_id
            if move.product_id == sale_line.product_id:
                quantity = move.product_uom._compute_quantity(
                    quantity,
                    sale_line.product_uom_id,
                    round=False,
                )
            else:
                # Phantom-kit/component moves can point to the kit sale line.
                # Convert their completion ratio into an equivalent sale quantity
                # instead of mixing quantities of different products.
                demand = move.product_uom_qty
                if float_is_zero(demand, precision_rounding=move.product_uom.rounding):
                    continue
                quantity = (quantity / demand) * sale_line.product_uom_qty
                component_equivalent_quantities[sale_line] = max(
                    component_equivalent_quantities[sale_line],
                    quantity,
                )
                continue
            quantities[sale_line] += quantity
        for sale_line, quantity in component_equivalent_quantities.items():
            quantities[sale_line] = max(quantities[sale_line], quantity)
        return quantities

    def _vv_sale_line_posted_invoice_quantity(self, sale_line):
        """Net quantity covered by posted invoices for one exact sale line."""
        self.ensure_one()
        quantity = 0.0
        for invoice_line in sale_line.invoice_lines.filtered(
            lambda line: line.move_id.state == "posted"
            and line.move_id.company_id == self.company_id
            and line.move_id.move_type in ("out_invoice", "out_refund")
        ):
            invoice = invoice_line.move_id
            # A fully reversed customer invoice provides no delivery coverage.
            if invoice.move_type == "out_invoice" and invoice.payment_state == "reversed":
                continue
            line_uom = invoice_line.product_uom_id or sale_line.product_uom_id
            line_quantity = line_uom._compute_quantity(
                invoice_line.quantity,
                sale_line.product_uom_id,
                round=False,
            )
            quantity += line_quantity if invoice.move_type == "out_invoice" else -line_quantity
        return quantity

    def _vv_manual_invoice_quantities(self):
        """Net invoiced quantities by product, in each product's default UoM."""
        self.ensure_one()
        quantities = defaultdict(float)
        invoice = self.vv_manual_invoice_id
        if not invoice or invoice not in self._vv_get_posted_invoices():
            return quantities
        for line in invoice.invoice_line_ids.filtered(
            lambda l: l.product_id and l.display_type == "product"
        ):
            quantity = line.product_uom_id._compute_quantity(
                line.quantity,
                line.product_id.uom_id,
                round=False,
            )
            quantities[line.product_id] += quantity
        return quantities

    def _vv_manual_already_delivered_quantities(self):
        """Quantities already consumed from the selected manual invoice."""
        self.ensure_one()
        quantities = defaultdict(float)
        if not self.vv_manual_invoice_id:
            return quantities
        previous_pickings = self.search([
            ("id", "!=", self.id),
            ("state", "=", "done"),
            ("picking_type_id.code", "=", "outgoing"),
            ("vv_manual_invoice_id", "=", self.vv_manual_invoice_id.id),
            ("company_id", "=", self.company_id.id),
        ])
        for move in previous_pickings.move_ids.filtered(
            lambda m: m.state == "done" and not m.sale_line_id
        ):
            quantity = self._vv_move_quantity(move)
            quantity = move.product_uom._compute_quantity(
                quantity,
                move.product_id.uom_id,
                round=False,
            )
            quantities[move.product_id] += quantity
        return quantities

    def _vv_manual_current_quantities(self):
        """Non-sale quantities in this picking, in product default UoM."""
        self.ensure_one()
        quantities = defaultdict(float)
        for move in self.move_ids.filtered(lambda m: m.state != "cancel" and not m.sale_line_id):
            quantity = self._vv_move_quantity(move)
            if float_is_zero(quantity, precision_rounding=move.product_uom.rounding):
                continue
            quantity = move.product_uom._compute_quantity(
                quantity,
                move.product_id.uom_id,
                round=False,
            )
            quantities[move.product_id] += quantity
        return quantities

    def _vv_get_invoice_coverage_issues(self):
        """Return every quantity that would be delivered without invoice cover."""
        self.ensure_one()
        issues = []

        # Sale deliveries are controlled by their exact sale lines. A manually
        # selected invoice must never bypass an under-invoiced sale line.
        for sale_line, current_qty in self._vv_sale_line_current_quantities().items():
            invoiced_qty = self._vv_sale_line_posted_invoice_quantity(sale_line)
            previously_delivered = sale_line.qty_delivered
            total_after_validation = previously_delivered + current_qty
            if float_compare(
                total_after_validation,
                invoiced_qty,
                precision_rounding=sale_line.product_uom_id.rounding,
            ) > 0:
                issues.append({
                    "product": sale_line.product_id.display_name,
                    "uom": sale_line.product_uom_id.display_name,
                    "invoiced": invoiced_qty,
                    "delivered": previously_delivered,
                    "current": current_qty,
                    "uncovered": total_after_validation - invoiced_qty,
                    "sale_order": sale_line.order_id.name,
                })

        # Pickings created directly in Inventory have no sale line. In that
        # case, consume the quantities of the manually linked posted invoice.
        manual_invoiced = self._vv_manual_invoice_quantities()
        manual_delivered = self._vv_manual_already_delivered_quantities()
        for product, current_qty in self._vv_manual_current_quantities().items():
            invoiced_qty = manual_invoiced.get(product, 0.0)
            previously_delivered = manual_delivered.get(product, 0.0)
            total_after_validation = previously_delivered + current_qty
            if float_compare(
                total_after_validation,
                invoiced_qty,
                precision_rounding=product.uom_id.rounding,
            ) > 0:
                issues.append({
                    "product": product.display_name,
                    "uom": product.uom_id.display_name,
                    "invoiced": invoiced_qty,
                    "delivered": previously_delivered,
                    "current": current_qty,
                    "uncovered": total_after_validation - invoiced_qty,
                    "sale_order": False,
                })
        return issues

    def _vv_coverage_error_message(self, issues):
        self.ensure_one()
        detail_lines = []
        for issue in issues:
            origin = _(" | Pedido: %(order)s", order=issue["sale_order"]) if issue["sale_order"] else ""
            detail_lines.append(_(
                "• %(product)s%(origin)s\n"
                "  Facturado: %(invoiced).2f %(uom)s | Ya entregado: %(delivered).2f | "
                "Entrega actual: %(current).2f | Sin cobertura: %(uncovered).2f",
                product=issue["product"],
                origin=origin,
                invoiced=issue["invoiced"],
                delivered=issue["delivered"],
                current=issue["current"],
                uncovered=issue["uncovered"],
                uom=issue["uom"],
            ))
        return _(
            "No es posible validar la entrega %(picking)s porque las cantidades a "
            "despachar superan las cantidades facturadas y publicadas.\n\n%(details)s\n\n"
            "Publique la factura correspondiente al saldo pendiente o solicite una "
            "autorización excepcional a un usuario del grupo "
            "'Autorizar Despachos sin Factura'.",
            picking=self.display_name,
            details="\n".join(detail_lines),
        )

    def _vv_check_delivery_invoice(self):
        for picking in self:
            if not picking._vv_requires_invoice_control():
                continue
            if picking.vv_without_invoice_authorized:
                continue
            issues = picking._vv_get_invoice_coverage_issues()
            if issues:
                raise UserError(picking._vv_coverage_error_message(issues))

    def button_validate(self):
        self._vv_check_delivery_invoice()
        return super().button_validate()

    def action_vv_authorize_without_invoice(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "agru_delivery_invoice_control.group_authorize_delivery_without_invoice"
        ):
            raise UserError(_("No tiene permiso para autorizar despachos sin factura."))
        if not self._vv_requires_invoice_control():
            raise UserError(_("Sólo se pueden autorizar entregas pendientes de validación."))
        if not self._vv_get_invoice_coverage_issues():
            raise UserError(_("La entrega está completamente cubierta por facturas publicadas y no requiere autorización."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Autorizar despacho sin factura"),
            "res_model": "agru.delivery.without.invoice.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_picking_id": self.id},
        }

    def write(self, vals):
        # A previous exception must never remain reusable after a completed
        # delivery is reopened, or after its key business data changes.
        reset_authorization = False
        if {"partner_id", "company_id", "picking_type_id"} & set(vals):
            reset_authorization = True
        if vals.get("state") == "draft" and any(p.state == "done" for p in self):
            reset_authorization = True
        if reset_authorization and "vv_without_invoice_authorized" not in vals:
            vals = dict(vals, **{
                "vv_without_invoice_authorized": False,
                "vv_without_invoice_authorized_by_id": False,
                "vv_without_invoice_authorized_date": False,
                "vv_without_invoice_reason": False,
            })
        return super().write(vals)
