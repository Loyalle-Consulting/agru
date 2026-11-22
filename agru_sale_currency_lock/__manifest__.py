# -*- coding: utf-8 -*-
{
    'name': 'AGRU - Totalización Multi-Moneda con Tasa Sellada',
    'version': '19.0.2.0.0',
    'category': 'Sales',
    'summary': 'Permite totalizar cotizaciones/pedidos de venta en cualquier moneda activa, '
               'sellando la tasa de cambio al momento de la cotización.',
    'description': """
AGRU - Totalización Multi-Moneda con Tasa Sellada
======================================================
La lista de precios base se mantiene en su moneda de referencia (ej. USD).
Este módulo agrega a la Orden de Venta la posibilidad de elegir una
"Moneda de totalización" distinta (cualquier moneda activa del sistema).

- La moneda de cotización y la tasa se pueden editar libremente mientras
  el pedido esté en Presupuesto o Cotización enviada; las líneas se
  recalculan automáticamente, sin importar cuántas veces se alterne de
  moneda (siempre se recalcula desde el precio original, nunca se
  compone sobre un valor ya convertido).
- Al confirmar el pedido, moneda y tasa quedan selladas.
- Si el pedido vuelve a estado de cotización, se puede volver a editar
  (esto se basa en el campo 'state' real del pedido, no en una bandera
  propia, así que funciona sin importar qué acción se use para cambiar
  de estado).
- Agrega a la ficha del producto el campo "Moneda del precio base": el
  "Precio de venta" de Odoo no tiene moneda propia (siempre se asume
  moneda de la compañía); este campo permite declarar en qué moneda está
  ese precio en realidad, para que los productos sin regla propia en la
  lista de precios se conviertan bien al calcular una cotización.

Este módulo NO depende de eCommerce/sitio web y se puede instalar en
cualquier instancia. Para que los pedidos originados en la tienda online
fuercen automáticamente la moneda real de esa tienda, instalar además
el módulo puente 'agru_sale_currency_lock_website' (requiere que el
módulo 'website_sale' esté instalado).

Changelog 19.0.1.1.0: corrige una diferencia de uno o dos pesos que
podía aparecer en productos SIN regla propia en la lista de precios,
cuya moneda base (ficha) es distinta de la moneda de la lista pero
IGUAL a la moneda final de la cotización (ej. ficha en CLP, lista en
USD, cotización totalizada en CLP). Antes el precio pasaba dos veces
por conversión de moneda (base -> lista -> cotización) y perdía
precisión en el paso intermedio; ahora, en ese caso puntual, se
traspasa el precio de la ficha directo, sin ningún cálculo.
""",
    'author': 'Loyalle Consulting',
    'website': 'https://www.grupoloyalle.cl',
    'license': 'LGPL-3',
    'depends': ['sale'],
    'data': [
        'views/sale_order_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
}
