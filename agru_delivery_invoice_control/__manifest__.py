{
    "name": "AGRU - Control de Despachos con Factura",
    "version": "19.0.2.0.0",
    "category": "Inventory/Inventory",
    "summary": "Impide validar entregas sin una factura de cliente publicada",
    "author": "Loyalle Consulting",
    "license": "LGPL-3",
    "depends": ["stock", "sale_stock", "account"],
    "data": [
        "security/delivery_invoice_security.xml",
        "security/ir.model.access.csv",
        "wizard/delivery_without_invoice_wizard_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
}
