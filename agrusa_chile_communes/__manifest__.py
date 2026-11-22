{
    "name": "AGRUSA - Comunas de Chile",
    "version": "19.0.1.0.0",
    "category": "Contacts",
    "summary": "Mantenedor de comunas chilenas y selección por región en contactos",
    "author": "Loyalle Consulting",
    "license": "LGPL-3",
    "depends": ["contacts"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_country_commune_views.xml",
        "views/res_partner_views.xml",
        "data/load_communes.xml",
    ],
    "installable": True,
    "application": False,
}
