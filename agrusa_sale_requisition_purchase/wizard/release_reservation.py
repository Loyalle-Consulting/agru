# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError
from odoo.tools.float_utils import float_compare, float_is_zero


class AgrusaRequisitionRelease(models.TransientModel):
    _name = 'agrusa.requisition.release'
    _description = 'Liberación autorizada de reserva de requisición'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    line_id = fields.Many2one('sale.order.line', required=True, string='Línea de requisición')
    quantity = fields.Float(string='Cantidad a liberar', required=True, digits='Product Unit')

    def action_release(self):
        self.ensure_one()
        if not self.env.user.has_group('agrusa_sale_requisition_purchase.group_requisition_release'):
            raise AccessError(_('No tiene autorización para liberar reservas de requisición.'))
        line = self.line_id
        if line.order_id != self.order_id or line.agrusa_supply_origin != 'requisition' or line.state != 'sale':
            raise UserError(_('Seleccione una línea de Requisición de un pedido confirmado.'))
        rounding = line.product_uom_id.rounding
        if float_compare(self.quantity, 0, precision_rounding=rounding) <= 0:
            raise UserError(_('La cantidad a liberar debe ser mayor que cero.'))
        moves = line.move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.location_id.usage == 'internal'
            and m.location_dest_id.usage == 'customer'
        )
        # The release changes the delivery demand, not the PO quantity or the sale.
        # The uncommitted purchase remainder will become common stock on receipt.
        remaining = sum(m.product_uom._compute_quantity(m.product_uom_qty, line.product_uom_id) for m in moves)
        if float_compare(self.quantity, remaining, precision_rounding=rounding) > 0:
            raise UserError(_('No puede liberar más de %.3f unidades pendientes.') % remaining)
        pending = self.quantity
        for move in moves:
            if float_is_zero(pending, precision_rounding=rounding):
                break
            move_qty = move.product_uom._compute_quantity(move.product_uom_qty, line.product_uom_id)
            released = min(pending, move_qty)
            new_qty = move_qty - released
            if move.state == 'assigned':
                move._do_unreserve()
            if float_is_zero(new_qty, precision_rounding=rounding):
                move._action_cancel()
            else:
                move.write({'product_uom_qty': line.product_uom_id._compute_quantity(new_qty, move.product_uom)})
            pending -= released
        line.write({'agrusa_requisition_released_qty': line.agrusa_requisition_released_qty + self.quantity})
        line.order_id.message_post(body=_('Liberación autorizada de Requisición: usuario %s, producto %s, línea %s, cantidad liberada %.3f %s, cantidad pendiente comprometida %.3f %s.') % (
            self.env.user.display_name, line.product_id.display_name, line.id,
            self.quantity, line.product_uom_id.name,
            remaining - self.quantity, line.product_uom_id.name,
        ))
        return {'type': 'ir.actions.act_window_close'}
