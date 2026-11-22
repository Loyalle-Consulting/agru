{
    'name': 'AGRUSA - Seguridad de creacion de productos',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Autoriza creacion de productos por grupo y bloquea crear/editar desde selectores',
    'author': 'Loyalle Consulting',
    'license': 'LGPL-3',
    'depends': ['product', 'sale_management', 'purchase', 'stock', 'account'],
    'data': ['security/product_security_groups.xml'],
    'installable': True,
    'application': False,
}
