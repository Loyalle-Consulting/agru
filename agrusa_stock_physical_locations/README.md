# AGRUSA - Posiciones fisicas de bodega (Odoo 19)

## Alcance
- Mantenedor de posiciones: Inventario > Configuracion > Posiciones de Bodega.
- Codigo: P{pasillo}-R{rack}-L{longitudinal}-N{nivel}.
- Una posicion fisica puede corresponder a ubicaciones internas diferentes de WH, WH2, WH3 y WH4.
- Control de posiciones en lineas de movimientos al validar recepciones, entregas y transferencias.

## IMPORTANTE: despliegue piloto / limitaciones
Esta entrega es una **base tecnica para pruebas en STAGING**, NO un modulo listo para produccion.
El mantenedor permite crear posiciones fisicas. La vinculacion automatica de posiciones
con las ubicaciones de cada bodega se implementa como metodo de modelo
`get_warehouse_location(warehouse)`, pero **todavia no hay un asistente de picking**
que seleccione posiciones, cree la vinculacion y ajuste automaticamente las lineas
operativas. El usuario debe configurar las ubicaciones y las lineas de movimiento
correctamente antes de validar. Tampoco hay migracion de stock existente ni
adaptacion de reservas comerciales a las sububicaciones. No activar el control
sobre operaciones reales antes de completar esas fases.

## Riesgos conocidos que requieren validacion en STAGING
- Confirmar XML ID de vista detallada y menu de Configuracion en Odoo 19.
- Verificar comportamiento de `_action_done` y `button_validate` en todas las rutas.
- Validar recepciones con lotes, salidas reservadas, backorders y movimientos parciales.
- Evaluar reserva exclusiva de requisiciones: el codigo existente exige coincidencia
  exacta de ubicacion entre recepcion y entrega, lo que puede entrar en conflicto
  con posiciones hijas.
- Verificar guias DTE 52, control de facturacion y operaciones multi-bodega.

## Instalacion
Copiar carpeta al repositorio de addons, subir mediante GitHub/Odoo.sh y probar
primero en una rama de STAGING aislada. No actualizar manifiestos de otros modulos.

## Actualizacion v2 (STAGING exclusivamente)
- Selector de posicion fisica origen/destino en la vista detallada heredada.
- Al guardar una linea con posicion, crea o reutiliza la sububicacion de la bodega.
- No modifica manifiestos de otros modulos.
- **Limitacion critica**: no migra existencias preexistentes, no reasigna reservas previas,
  y no cubre necesariamente todas las vistas Odoo 19 de detalles (comprobar en STAGING).
- **NO validar salidas con reservas previas** hasta probar el flujo integral.
- La instalacion y compilacion Python no sustituyen pruebas Odoo de XML ni de negocio.


## v3 - Vista de operaciones detalladas
Se hereda adicionalmente `stock.view_stock_move_line_operation_tree`, la lista seleccionada por `list_view_ref` en `stock.view_stock_move_operations`. Los campos de posicion se muestran en la ventana de Detalles. Antes de validar movimientos, verificar mapeo de ubicaciones, reservas y cantidades en STAGING.

## Actualizacion de reglas y columnas (STAGING)
- Recepcion: exige posicion de destino; salida: exige posicion de origen; transferencia: ambas.
- Una posicion admite multiples productos y bodegas virtuales separadas.
- Columnas informativas no almacenadas: existencia fisica y disponible no reservado.
- En transferencias se consultan las existencias de origen; en recepciones las de destino.
- El calculo suma quants del producto en la sububicacion exacta y bodega Odoo, sin mezclar lotes ni propietarios.
- Las cantidades no reservadas NO sustituyen la validacion estandar de reservas de Odoo.
- No cambia version de __manifest__.py.
- IMPORTANTE: pendientes pruebas de reservas de requisiciones, transferencias con misma posicion, lotes y backorders. No apto para produccion.
