# AGRUSA - Referencia de provisión

Campo informativo editable en orden de compra y visible en recepciones vinculadas mediante stock.picking.purchase_id. No modifica operaciones contables ni de inventario. La referencia se refleja dinámicamente en las recepciones relacionadas.

## Prueba
1. Crear OC con referencia de provisión.
2. Confirmar OC y abrir recepción generada.
3. Comprobar que la referencia aparece en la recepción.
4. Cambiar la referencia de la OC y verificar la actualización en la recepción.

Nota: si una recepción agrupa movimientos de varias órdenes de compra, `purchase_id` puede no identificar una única OC; revisar ese caso antes de utilizar este campo como identificador único.
