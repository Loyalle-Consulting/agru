from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    agru_warehouse_stock = fields.Json(string="Detalle técnico de stock por bodega", compute="_compute_vv_stock_visibility")
    agru_warehouse_stock_display = fields.Char(string="Stock por bodega", compute="_compute_vv_stock_visibility")
    vv_stock_physical = fields.Float(string="Stock físico total", compute="_compute_vv_stock_visibility")
    vv_outgoing_qty = fields.Float(string="Salidas previstas", compute="_compute_vv_stock_visibility")
    vv_unreserved_out_qty = fields.Float(string="Salidas aún no reservadas", compute="_compute_vv_stock_visibility")
    vv_reserved_out_qty = fields.Float(string="Salidas reservadas", compute="_compute_vv_stock_visibility")
    vv_free_qty = fields.Float(string="Disponible inmediato", compute="_compute_vv_stock_visibility")
    vv_po_pending_qty = fields.Float(string="OC por recibir", compute="_compute_vv_stock_visibility")
    vv_forecast_qty = fields.Float(string="Pronosticado", compute="_compute_vv_stock_visibility")

    @api.depends("product_id", "order_id.company_id")
    def _compute_vv_stock_visibility(self):
        for line in self:
            values = {
                "agru_warehouse_stock": [],
                "agru_warehouse_stock_display": "",
                "vv_stock_physical": 0.0,
                "vv_outgoing_qty": 0.0,
                "vv_unreserved_out_qty": 0.0,
                "vv_reserved_out_qty": 0.0,
                "vv_free_qty": 0.0,
                "vv_po_pending_qty": 0.0,
                "vv_forecast_qty": 0.0,
            }
            if line.product_id:
                company = line.order_id.company_id or line.company_id or self.env.company
                product = line.product_id.with_company(company)
                values.update({
                    "agru_warehouse_stock": product.agru_warehouse_stock,
                    "agru_warehouse_stock_display": product.agru_warehouse_stock_display,
                    "vv_stock_physical": product.qty_available,
                    "vv_outgoing_qty": product.outgoing_qty,
                    "vv_unreserved_out_qty": product.vv_unreserved_out_qty,
                    "vv_reserved_out_qty": product.vv_reserved_out_qty,
                    "vv_free_qty": product.free_qty,
                    "vv_po_pending_qty": product.vv_po_pending_qty,
                    "vv_forecast_qty": product.virtual_available,
                })
            for field_name, value in values.items():
                line[field_name] = value
