{
    'name': 'AGRUSA - Posiciones Fisicas de Bodega',
    'version': '19.0.1.0.0',
    'summary': 'Posiciones compartidas y control de ubicacion fisica en operaciones',
    'category': 'Inventory/Inventory',
    'author': 'Grupo Loyalle',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/physical_position_views.xml',
        'views/stock_move_line_views.xml',
        'views/position_lookup_views.xml',
    ],
    'installable': True,
    'application': False,
}
