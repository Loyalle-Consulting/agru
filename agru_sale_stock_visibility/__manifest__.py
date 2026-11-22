{
    "name": "AGRU - Visibilidad de Stock en Ventas",
    "version": "19.0.2.0.0",
    "category": "Sales/Inventory",
    "summary": "Desglose comercial de stock por bodega en selección de productos y ventas",
    "author": "Loyalle Consulting",
    "license": "LGPL-3",
    "depends": ["sale_stock", "purchase_stock"],
    "data": [
        "views/product_product_views.xml",
        "views/sale_order_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "agru_sale_stock_visibility/static/src/widgets/qty_at_date_widget.js",
            "agru_sale_stock_visibility/static/src/widgets/qty_at_date_widget.xml",
            "agru_sale_stock_visibility/static/src/widgets/forecasted_visibility.xml",
        ],
    },
    "installable": True,
    "application": False,
}
