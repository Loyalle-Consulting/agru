{
    'name': 'AGRUSA - Control y autorizacion de credito',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': 'Loyalle Consulting',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'account', 'mail', 'agrusa_sale_delivery_date'],
    'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/credit_views.xml'],
    'installable': True,
    'application': False,
}
