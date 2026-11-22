from collections import defaultdict

from odoo import api, models


def _vv_add_visibility(env, result, docids, is_template=False):
    """Add AGRU availability data without altering Odoo forecast calculations."""
    docs = result.get("docs")
    if not docs or not isinstance(docs, dict):
        return result

    if is_template:
        products = env["product.product"].search([
            ("product_tmpl_id", "in", docids),
            ("active", "=", True),
        ])
    else:
        products = env["product.product"].browse(docids).exists()
    if not products:
        return result

    company = env.company
    products = products.with_company(company)
    warehouses = env["stock.warehouse"].sudo().search(
        [("company_id", "=", company.id)], order="sequence, id"
    )
    qty_by_wh = {wh.id: 0.0 for wh in warehouses}
    for product in products:
        for item in (product.agru_warehouse_stock or []):
            if item.get("id") in qty_by_wh:
                qty_by_wh[item["id"]] += item.get("qty", 0.0) or 0.0
    warehouse_stock = [
        {"id": wh.id, "name": wh.name, "code": wh.code, "qty": qty_by_wh[wh.id]}
        for wh in warehouses
    ]

    report_products = docs.get("product") or {}
    quantity_on_hand = incoming_qty = outgoing_qty = free_qty = virtual_available = 0.0
    for product in products:
        values = report_products.get(product.id) or {}
        quantity_on_hand += values.get("quantity_on_hand", 0.0) or 0.0
        incoming_qty += values.get("incoming_qty", 0.0) or 0.0
        outgoing_qty += values.get("outgoing_qty", 0.0) or 0.0
        free_qty += values.get("free_qty", 0.0) or 0.0
        virtual_available += values.get("virtual_available", 0.0) or 0.0

    reserved_out_qty = max(quantity_on_hand - free_qty, 0.0)
    unreserved_out_qty = max(outgoing_qty - reserved_out_qty, 0.0)

    po_pending_by_product = defaultdict(float)
    po_domain = [
        ("product_id", "in", products.ids),
        ("company_id", "=", company.id),
        ("order_id.state", "in", ["purchase", "done"]),
    ]
    warehouse_id = env.context.get("warehouse_id")
    if warehouse_id:
        po_domain.append(("order_id.picking_type_id.warehouse_id", "=", warehouse_id))
    po_lines = env["purchase.order.line"].sudo().search(po_domain)
    for line in po_lines:
        pending = max(line.product_qty - line.qty_received, 0.0)
        if pending:
            po_pending_by_product[line.product_id.id] += line.product_uom_id._compute_quantity(
                pending, line.product_id.uom_id
            )

    # Vista comercial por linea de OC: NO altera el pronostico ni las reservas fisicas.
    # Mostrar exclusivamente importaciones marcadas para el flujo AGRUSA.
    commercial_rows = []
    if ("agrusa_import_purchase_line_id" in env["sale.order.line"]._fields
            and "agrusa_is_import" in env["purchase.order"]._fields):
        SaleLine = env["sale.order.line"].sudo()
        import_lines = po_lines.filtered(lambda l: l.order_id.agrusa_is_import)
        # Se consulta en una sola operacion para evitar una busqueda por OC.
        committed = defaultdict(float)
        if import_lines:
            sale_lines = SaleLine.search([
                ("agrusa_import_purchase_line_id", "in", import_lines.ids),
                ("order_id.state", "in", ["sale", "done"]),
            ])
            for sale_line in sale_lines:
                purchase_line = sale_line.agrusa_import_purchase_line_id
                committed[purchase_line.id] += sale_line.product_uom_id._compute_quantity(
                    sale_line.product_uom_qty, purchase_line.product_uom_id
                )
        for purchase_line in import_lines.sorted(key=lambda l: (l.order_id.name or "", l.id)):
            ordered = purchase_line.product_qty
            received = purchase_line.qty_received
            reserved = committed[purchase_line.id]
            commercial_rows.append({
                "id": purchase_line.id,
                "order": purchase_line.order_id.name or "-",
                "product": purchase_line.product_id.display_name or "-",
                "eta": purchase_line.date_planned.date().isoformat() if purchase_line.date_planned else "-",
                "ordered": round(ordered, 2),
                "received": round(received, 2),
                "pending": round(max(ordered - received, 0.0), 2),
                "committed": round(reserved, 2),
                "available": round(max(ordered - reserved, 0.0), 2),
                "uom": purchase_line.product_uom_id.name or "",
            })

    uom_names = products.mapped("uom_id.name")
    uom = uom_names[0] if len(set(uom_names)) == 1 else ""
    docs["vv_visibility"] = {
        "warehouse_stock": warehouse_stock,
        "commercial_import_rows": commercial_rows,
        "physical_qty": quantity_on_hand,
        "outgoing_qty": outgoing_qty,
        "unreserved_out_qty": unreserved_out_qty,
        "reserved_out_qty": reserved_out_qty,
        "available_qty": free_qty,
        "po_pending_qty": sum(po_pending_by_product.values()),
        "forecast_qty": virtual_available,
        "incoming_qty": incoming_qty,
        "uom": uom,
    }
    return result


class StockForecastedProductProduct(models.AbstractModel):
    _inherit = "stock.forecasted_product_product"

    @api.model
    def get_report_values(self, docids, data=None):
        return _vv_add_visibility(self.env, super().get_report_values(docids, data=data), docids, False)


class StockForecastedProductTemplate(models.AbstractModel):
    _inherit = "stock.forecasted_product_template"

    @api.model
    def get_report_values(self, docids, data=None):
        return _vv_add_visibility(self.env, super().get_report_values(docids, data=data), docids, True)
