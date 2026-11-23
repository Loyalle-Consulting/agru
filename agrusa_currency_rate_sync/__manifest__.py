{
    'name': 'AGRUSA - Paridades Banco Central',
    'version': '19.0.1.0.0',
    'author': 'Loyalle Consulting',
    'category': 'Accounting/Accounting',
    'summary': 'Actualización de paridades EUR y USD desde el Banco Central de Chile',
    'depends': ['account', 'currency_rate_live'],
    'data': [
        'security/ir.model.access.csv',
        'security/rules.xml',
        'views/views.xml',
        'data/cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
