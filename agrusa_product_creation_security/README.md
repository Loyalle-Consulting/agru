# AGRUSA - Seguridad de creación de productos (Odoo 19)

## Alcance
- Grupo nuevo: **AGRUSA - Creacion de productos autorizada**.
- Usuarios fuera del grupo no pueden crear `product.template` ni `product.product` por ORM normal.
- Las vistas finales de Ventas, Compras, Inventario y Facturación reciben opciones `no_create`, `no_create_edit`, `no_quick_create` y `no_open` en selectores de productos. Aplica también a usuarios del grupo.
- No se modifican las ACL ni los grupos estándar de Odoo, ni se cambia el manifiesto de otros módulos.

## Instalación
1. Copiar la carpeta `agrusa_product_creation_security` a la raíz de addons personalizados de la rama temporal.
2. Actualizar lista de aplicaciones e instalar el módulo.
3. En Ajustes / Usuarios y compañías / Grupos, buscar `AGRUSA - Creacion de productos autorizada` y asignar exclusivamente a los usuarios autorizados.
4. **IMPORTANTE:** los usuarios autorizados también necesitan los permisos estándar de Odoo para crear productos (grupo `Productos / Crear`). La pertenencia al grupo AGRUSA no concede por sí sola ACL estándar.
5. Probar con usuario no autorizado y autorizado; no usar Administrator como única prueba.

## Alcance de protección
La creación se bloquea en servidor para usuarios sin el grupo AGRUSA. La prohibición de abrir/editar desde selectores es una restricción de interfaz; no constituye una prohibición general de modificar productos desde su mantenedor o vía API. No se altera `write()` porque Odoo utiliza actualizaciones de producto durante procesos operativos, y bloquearlo requiere una auditoría separada de campos.

## Consideraciones
- `sudo()` / superusuario omite la verificación para no romper procesos automáticos internos.
- Se mantienen los permisos estándar de escritura y eliminación existentes. Si se necesita impedir edición/borrado fuera del grupo también en servidor, requiere fase adicional y pruebas de regresión.
- En vistas con `options` expresados dinámicamente que no se pueden interpretar de forma literal, se conservan intactos y se recomienda revisar esas vistas concretas.
