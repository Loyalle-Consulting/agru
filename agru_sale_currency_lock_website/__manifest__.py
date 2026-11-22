# -*- coding: utf-8 -*-
{
    'name': 'AGRU - Totalización Multi-Moneda: Integración eCommerce',
    'version': '19.0.2.0.0',
    'category': 'Sales',
    'summary': 'Fuerza automáticamente la moneda real de la tienda en los pedidos '
               'originados en el sitio web, sin intervención manual.',
    'description': """
AGRU - Totalización Multi-Moneda: Integración eCommerce
=============================================================
Módulo puente entre 'agru_sale_currency_lock' y 'website_sale'.

Se instala APARTE del módulo base a propósito: no todos los clientes de
Loyalle tienen el sitio web/eCommerce activado, y el campo 'website_id'
que usa esta lógica solo existe cuando 'website_sale' está instalado. Si
esta pieza estuviera mezclada en el módulo base, cualquier cliente sin
eCommerce vería errores al actualizar el módulo.

Comportamiento: todo pedido con website_id (originado en la tienda
online) fuerza automáticamente la moneda de cotización a la moneda de
la COMPAÑÍA (Ajustes → Empresas — no se inventa ningún parámetro
nuevo), sin que nadie tenga que elegir nada. Esto funciona sin importar
cuántas listas de precio diferenciadas por cliente existan (Default,
VIP, mayorista, etc.) ni en qué moneda esté cada una: a propósito NO se
usa website.currency_id, porque ese campo depende de la lista de
precios activa en cada sesión (cambiaría según qué lista esté usando
cada cliente). Cubre tanto la creación del carrito como cada
actualización posterior (agregar productos, cambiar de lista de precios
al iniciar sesión, etc.).
""",
    'author': 'Loyalle Consulting',
    'website': 'https://www.grupoloyalle.cl',
    'license': 'LGPL-3',
    'depends': ['agru_sale_currency_lock', 'website_sale'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
