{
    'name': 'AGRUSA - Entregas por Producto',
    'version': '19.0.1.0.0',
    'summary': 'Consulta de entregas de salida por movimiento, producto y fecha',
    'category': 'Inventory/Inventory',
    'author': 'Loyalle Consulting',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock', 'agrusa_sale_delivery_date', 'agrusa_import_sale_pricing'],
    'data': ['views/stock_move_delivery_views.xml'],
    'installable': True,
    'application': False,
}
