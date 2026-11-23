{
    'name': 'AGRUSA - Despacho exclusivo desde Bodega Principal',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'Loyalle Consulting'
    'summary': 'Transferencia interna controlada antes del despacho desde WH',
    'license': 'LGPL-3',
    'depends': [
        'stock', 'sale_stock',
        'agrusa_sale_supply_origin',
        'agrusa_sale_requisition_purchase',
        'agrusa_import_sale_pricing',
        'agrusa_stock_physical_locations',
        'agru_delivery_invoice_control',
    ],
    'data': ['views/stock_picking_views.xml'],
    'installable': True,
    'application': False,
}
