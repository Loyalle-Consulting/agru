# AGRUSA - Despacho exclusivo desde Bodega Principal

**PROTOTIPO TECNICO PARA REVISION. NO INSTALAR TODAVIA EN PRODUCCION.**

Genera transferencia interna al validar una entrega secundaria, requiere confirmacion manual y bloquea la entrega hasta que el traslado este realizado.

## Limites deliberados de esta primera version
- Solo entregas nuevas, completamente reservadas, con una unica ubicacion fisica de origen y sin movimientos posteriores realizados.
- No procesa backorders, entregas mixtas ni parciales. Bloquea estos casos en lugar de alterar datos.
- La transferencia debe recibir una posicion fisica de destino en WH, seleccionada manualmente en operaciones detalladas.
- Tras la transferencia, revisar las posiciones de origen de la entrega y sus lotes antes de validar.
- Debe probarse con Tránsito, Requisiciones y Consignaciones, incluyendo controles de importacion, facturacion y posiciones.
- El comportamiento del botón Validar y los asistentes de validacion debe comprobarse en Odoo.sh STAGING.
- No emitir DTE interno automáticamente: el campo l10n_cl_internal_dispatch no se establece.

## Instalacion propuesta
Copiar la carpeta del modulo a la rama de STAGING en GitHub; actualizar lista de aplicaciones e instalar. No editar los manifests de modulos existentes.
