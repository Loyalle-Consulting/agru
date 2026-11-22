# AGRUSA - Gestion masiva de tarifas (Odoo 19)

Instalar como modulo independiente en STAGING. Dependencias: sale_management, product, mail; libreria Python openpyxl (disponibilidad a comprobar en Odoo.sh).

Acceso: asignar grupo **AGRUSA - Administrar tarifas masivas** al usuario autorizado. Menu AGRUSA - Tarifas masivas.

Flujo: seleccionar tarifa > Exportar Excel > modificar hoja Tarifa > adjuntar XLSX > Validar y previsualizar > corregir errores > Aplicar cambios. Se registran lotes y detalles antes/despues.

**Reglas**: `id_regla` existente actualiza solo dentro de tarifa seleccionada; vacio crea nueva. No se eliminan reglas. Para nuevas reglas, usar variante, producto, categoria o global. Las fechas son opcionales. La columna `calculo` admite fixed, percentage y formula.

**Seguridad**: probar en STAGING con respaldo; maximo 5000 filas; confirmar que tarifas avanzadas se calculan correctamente. El modulo no modifica ventas existentes, OC ni reservas.

**Pruebas**: 1) exportar tarifa EUR; 2) editar precio fijo existente; 3) crear regla nueva; 4) verificar validacion de codigo inexistente; 5) comprobar historial; 6) cotizar producto sin OC y con OC.
