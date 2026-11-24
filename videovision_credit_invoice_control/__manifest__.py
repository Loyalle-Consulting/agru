# -*- coding: utf-8 -*-
{
    'name': 'Video Vision - Crédito controlado al facturar',
    'version': '19.0.1.2.0',
    'category': 'Sales/Sales',
    'summary': 'El bloqueo por línea de crédito y por mora se aplica al crear y al publicar la '
               'factura, no al confirmar el pedido. "Pendiente de aprobación" por pedido.',
    'description': """
Video Vision - Crédito controlado al facturar
=============================================
Complemento de videovision_credit_control (audios de Francisco y reunión 05-nov-2026).
No modifica el módulo base.

- Confirmar el pedido confirma y reserva stock siempre. Desde 19.0.1.1.0 (reunión 12-nov), si el
  cliente está moroso o sobre la línea, el pedido queda de inmediato "Pendiente de aprobación" y el
  botón "Crear factura" se muestra deshabilitado hasta que un responsable lo apruebe.
- Revisión diaria (acción planificada): pedidos por facturar cuyo cliente cayó en mora pasan a
  pendientes; los pendientes cuyo cliente ya cumple se liberan.
- Crédito utilizado = facturas impagas + cheques en cartera − saldos a favor.
  "Pedidos por facturar" se muestra solo como dato (ajuste apagado por defecto).
- "Crear factura": se evalúa el monto que se va a facturar (factura regular o
  anticipo). Si el cliente está moroso o supera la línea, NO se crea la factura y
  el pedido queda "Pendiente de aprobación" con su motivo, detalle, actividad al
  responsable de crédito y aviso al vendedor.
- Aprobación por pedido: vale para TODAS las facturas del pedido mientras su
  total no supere el monto aprobado. Si se suben cantidades por sobre ese
  monto, se vuelve a pedir aprobación.
- Al publicar una factura no cubierta por aprobación se vuelve a revisar (por si
  el borrador se creó días antes y el cliente cayó en mora). Facturas sin pedido:
  solo un aprobador de crédito puede publicarlas si no pasan el control.
- Menú "Pendientes de aprobación"; filtro "Reserva con problema de crédito" en la búsqueda
  (el menú propio se quitó en 19.0.1.1.0).
- Ficha del cliente: condiciones de crédito visibles para todos (tolerancias
  incluidas), editables solo por "Administrar crédito de clientes".
- Al instalar: las cotizaciones que estaban retenidas por crédito se liberan.
- Reunión 19-nov-2026 (19.0.1.2.0): el estado de crédito se recalcula con cada movimiento del
  cliente, no solo en la revisión diaria: al confirmar un pedido (revisa también sus otros pedidos),
  al registrar una factura, nota de crédito, cobro, comprobante o protesto, al conciliar y al deshacer
  una conciliación. Retiene los pedidos por facturar de clientes que cayeron en mora o sobre la línea y
  libera los pendientes de clientes que se pusieron al día (con aviso al vendedor si está instalado el
  cobro inteligente). La revisión diaria se mantiene para el cambio de día.
""",
    'author': 'Loyalle Consulting',
    'website': 'https://www.grupoloyalle.cl',
    'license': 'LGPL-3',
    'depends': ['videovision_credit_control', 'sale_stock'],
    'data': [
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
