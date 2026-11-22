from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    agru_warehouse_stock = fields.Json(string="Stock por bodega", compute="_compute_vv_stock_visibility")
    agru_warehouse_stock_display = fields.Char(string="Stock por bodega", compute="_compute_vv_stock_visibility")
    vv_physical_qty = fields.Float(string="Stock físico total", compute="_compute_vv_stock_visibility")
    vv_outgoing_qty = fields.Float(string="Salidas previstas", compute="_compute_vv_stock_visibility")
    vv_unreserved_out_qty = fields.Float(string="Salidas sin reservar", compute="_compute_vv_stock_visibility")
    vv_reserved_out_qty = fields.Float(string="Salidas reservadas", compute="_compute_vv_stock_visibility")
    vv_available_qty = fields.Float(string="Disponible inmediato", compute="_compute_vv_stock_visibility")
    vv_po_pending_qty = fields.Float(string="OC por recibir", compute="_compute_vv_stock_visibility")
    vv_forecast_qty = fields.Float(string="Pronosticado", compute="_compute_vv_stock_visibility")

    @api.depends_context("company", "allowed_company_ids")
    @api.depends(
        "product_variant_ids",
        "product_variant_ids.agru_warehouse_stock",
        "product_variant_ids.vv_reserved_out_qty",
        "product_variant_ids.vv_unreserved_out_qty",
        "product_variant_ids.vv_po_pending_qty",
    )
    def _compute_vv_stock_visibility(self):
        company = self.env.company
        Warehouse = self.env["stock.warehouse"].sudo()
        warehouses = Warehouse.search([("company_id", "=", company.id)], order="sequence, id")
        for template in self:
            variants = template.product_variant_ids.with_company(company)
            qty_by_wh = {wh.id: 0.0 for wh in warehouses}
            for variant in variants:
                for item in (variant.agru_warehouse_stock or []):
                    if item.get("id") in qty_by_wh:
                        qty_by_wh[item["id"]] += item.get("qty", 0.0) or 0.0
            breakdown = [
                {"id": wh.id, "name": wh.name, "code": wh.code, "qty": qty_by_wh[wh.id]}
                for wh in warehouses
            ]
            template.agru_warehouse_stock = breakdown
            template.agru_warehouse_stock_display = " | ".join(
                f"{item['name']}: {item['qty']:g}" for item in breakdown
            )
            template.vv_physical_qty = sum(variants.mapped("qty_available"))
            template.vv_outgoing_qty = sum(variants.mapped("outgoing_qty"))
            template.vv_unreserved_out_qty = sum(variants.mapped("vv_unreserved_out_qty"))
            template.vv_reserved_out_qty = sum(variants.mapped("vv_reserved_out_qty"))
            template.vv_available_qty = sum(variants.mapped("free_qty"))
            template.vv_po_pending_qty = sum(variants.mapped("vv_po_pending_qty"))
            template.vv_forecast_qty = sum(variants.mapped("virtual_available"))
