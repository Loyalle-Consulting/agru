# AGRUSA - Documento de entrega / traslado sin valores

Instalar en Odoo 19 con dependencias `stock` y `l10n_cl_edi_stock`.

En Inventario, abrir una transferencia de salida o traslado interno y seleccionar **Imprimir > Documento de entrega / traslado sin valores**.

La opción puede aparecer también en otras transferencias por el enlace genérico a `stock.picking`; en recepciones, el reporte rechaza la impresión con un mensaje informativo.

Validar en STAGING: entrega preparada, entrega realizada, entrega parcial, traslado interno, observaciones Studio, lotes/series, varias páginas y multiempresa.

No reemplaza documentos tributarios ni modifica movimientos de stock.


Ajuste de presentación: tipografía compacta en encabezado y datos, contacto en una línea.
Timbre: solo muestra PDF417 auténtico del DTE de la misma transferencia cuando existen l10n_cl_sii_barcode y l10n_latam_document_number. No genera DTE ni reemplaza la guía tributaria.
