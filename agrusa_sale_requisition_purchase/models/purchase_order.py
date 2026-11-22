# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        result = super().button_confirm()
        for po in self:
            for pol in po.order_line.filtered('sale_line_id'):
                line = pol.sale_line_id
                if line.agrusa_supply_origin != 'requisition':
                    continue
                incoming = pol.move_ids.filtered(
                    lambda m: m.state not in ('done', 'cancel')
                    and m.product_id == line.product_id
                    and m.location_dest_id.usage == 'internal'
                    and m.company_id == line.company_id
                )
                # In a 3-step WH4 route, sale_line.move_ids points to PICK
                # (WH4/Stock -> WH4/Packing), not directly to Customers.
                # Link the purchase receipt to the first stock-consuming move.
                candidates = line.move_ids.filtered(
                    lambda m: m.state not in ('done', 'cancel')
                    and m.product_id == line.product_id
                    and m.company_id == line.company_id
                    and m.location_id.usage == 'internal'
                    and m.location_dest_id.usage == 'internal'
                    and not m.move_orig_ids
                )
                if not candidates:
                    # Also support a 1-step delivery route if configured.
                    candidates = line.move_ids.filtered(
                        lambda m: m.state not in ('done', 'cancel')
                        and m.product_id == line.product_id
                        and m.company_id == line.company_id
                        and m.location_id.usage == 'internal'
                        and m.location_dest_id.usage == 'customer'
                        and not m.move_orig_ids
                    )
                if not candidates and line.agrusa_requisition_released_qty >= line.product_uom_qty:
                    continue  # Fully released: incoming stock is no longer committed.
                if not incoming or not candidates:
                    raise UserError(_(
                        'Requisición: no se pudo enlazar la recepción de %s con el primer '
                        'movimiento de abastecimiento de %s. La compra se ha detenido '
                        'para evitar stock sin protección.'
                    ) % (po.name, line.order_id.name))
                # Do not attach unrelated receipt moves, and do not infer a
                # warehouse transfer when the actual stock locations differ.
                for move in candidates:
                    matching = incoming.filtered(
                        lambda m: m.location_dest_id == move.location_id
                    )
                    if not matching:
                        raise UserError(_(
                            'Requisición: la recepción %s no llega a la ubicación de '
                            'origen del movimiento %s de %s.'
                        ) % (po.name, move.id, line.order_id.name))
                    if move.state == 'assigned':
                        move._do_unreserve()
                    move.write({
                        'move_orig_ids': [(4, m.id) for m in matching],
                    })
                    if move.state == 'draft':
                        move._action_confirm()
        return result
