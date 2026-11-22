from collections import defaultdict

from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    agru_warehouse_stock = fields.Json(string="Stock por bodega", compute="_compute_agru_stock_visibility")
    agru_warehouse_stock_display = fields.Char(string="Stock por bodega", compute="_compute_agru_stock_visibility")
    vv_reserved_out_qty = fields.Float(string="Salidas reservadas", compute="_compute_agru_stock_visibility")
    vv_unreserved_out_qty = fields.Float(string="Salidas sin reservar", compute="_compute_agru_stock_visibility")
    vv_po_pending_qty = fields.Float(string="OC por recibir", compute="_compute_agru_stock_visibility")

    @api.depends_context("company", "allowed_company_ids")
    def _compute_agru_stock_visibility(self):
        for product in self:
            product.agru_warehouse_stock = []
            product.agru_warehouse_stock_display = ""
            product.vv_reserved_out_qty = 0.0
            product.vv_unreserved_out_qty = 0.0
            product.vv_po_pending_qty = 0.0

        if not self:
            return

        company = self.env.company
        products = self.with_company(company)
        product_ids = products.ids
        Warehouse = self.env["stock.warehouse"].sudo()
        Location = self.env["stock.location"].sudo()
        Quant = self.env["stock.quant"].sudo()
        POLine = self.env["purchase.order.line"].sudo()

        # Always read the real warehouses of the active company. No names,
        # codes or database IDs are hard-coded.
        warehouses = Warehouse.search([("company_id", "=", company.id)], order="sequence, id")
        stock_by_warehouse = {wh.id: defaultdict(float) for wh in warehouses}

        for wh in warehouses:
            locations = Location.search([
                ("id", "child_of", wh.lot_stock_id.id),
                ("usage", "=", "internal"),
            ])
            if not locations:
                continue
            groups = Quant._read_group(
                domain=[
                    ("product_id", "in", product_ids),
                    ("company_id", "=", company.id),
                    ("location_id", "in", locations.ids),
                ],
                groupby=["product_id"],
                aggregates=["quantity:sum"],
            )
            for product_rec, quantity in groups:
                stock_by_warehouse[wh.id][product_rec.id] = quantity or 0.0

        reserved_by_product = defaultdict(float)
        internal_locations = Location.search([
            ("company_id", "in", [False, company.id]),
            ("usage", "=", "internal"),
        ])
        if internal_locations:
            groups = Quant._read_group(
                domain=[
                    ("product_id", "in", product_ids),
                    ("company_id", "=", company.id),
                    ("location_id", "in", internal_locations.ids),
                ],
                groupby=["product_id"],
                aggregates=["reserved_quantity:sum"],
            )
            for product_rec, quantity in groups:
                reserved_by_product[product_rec.id] = quantity or 0.0

        po_pending_by_product = defaultdict(float)
        po_lines = POLine.search([
            ("product_id", "in", product_ids),
            ("company_id", "=", company.id),
            ("order_id.state", "in", ["purchase", "done"]),
        ])
        for line in po_lines:
            pending = max(line.product_qty - line.qty_received, 0.0)
            if not pending:
                continue
            qty = line.product_uom_id._compute_quantity(pending, line.product_id.uom_id)
            po_pending_by_product[line.product_id.id] += qty

        for product in products:
            breakdown = [
                {
                    "id": wh.id,
                    "name": wh.name,
                    "code": wh.code,
                    "qty": stock_by_warehouse[wh.id][product.id],
                }
                for wh in warehouses
            ]
            product.agru_warehouse_stock = breakdown
            product.agru_warehouse_stock_display = " | ".join(
                f"{item['name']}: {item['qty']:g}" for item in breakdown
            )
            reserved = reserved_by_product[product.id]
            outgoing = product.outgoing_qty
            product.vv_reserved_out_qty = reserved
            product.vv_unreserved_out_qty = max(outgoing - reserved, 0.0)
            product.vv_po_pending_qty = po_pending_by_product[product.id]
