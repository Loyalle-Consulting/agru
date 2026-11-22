/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { qtyAtDateWidget } from "@sale_stock/widgets/qty_at_date_widget";

patch(qtyAtDateWidget, {
    fieldDependencies: [
        ...qtyAtDateWidget.fieldDependencies,
        { name: "agru_warehouse_stock", type: "json" },
        { name: "vv_stock_physical", type: "float" },
        { name: "vv_outgoing_qty", type: "float" },
        { name: "vv_unreserved_out_qty", type: "float" },
        { name: "vv_reserved_out_qty", type: "float" },
        { name: "vv_free_qty", type: "float" },
        { name: "vv_po_pending_qty", type: "float" },
        { name: "vv_forecast_qty", type: "float" },
    ],
});
