{
    'name': 'AGRUSA - Requisiciones de venta a compras',
    'version': '19.0.1.1.0',
    'category': 'Sales',
    'summary': 'Precio Euro Fabrica y OC borrador al confirmar ventas de requisicion',
    'author': 'Loyalle Consulting',
    'license': 'LGPL-3',
    'depends': ['agrusa_sale_supply_origin', 'purchase_stock'],
    'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/release_reservation_views.xml', 'views/sale_order_views.xml'],
    'installable': True,
    'application': False,
}
