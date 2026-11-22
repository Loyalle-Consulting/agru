from odoo import _, models
from odoo.exceptions import AccessError, UserError


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def action_agrusa_reset_to_draft(self):
        if not self.env.user.has_group('agrusa_landed_cost_reset.group_landed_cost_reset'):
            raise AccessError(_('No tiene autorización para restablecer Costos en Destino.'))
        self.check_access('write')
        for cost in self:
            if cost.state != 'done':
                raise UserError(_('Solo se pueden restablecer documentos registrados.'))
            if cost.account_move_id:
                raise UserError(_('No se puede restablecer %s: tiene un asiento contable asociado. Utilice el procedimiento de reversión contable y de valoración correspondiente.') % cost.display_name)
            # La validación ejecuta _set_value() aun sin asiento contable.
            # Un ajuste sobre movimientos puede afectar el inventario sin crear asiento.
            if cost.valuation_adjustment_lines.filtered(lambda line: line.move_id):
                raise UserError(_('No se puede restablecer %s: existen ajustes asociados a movimientos de inventario. La ausencia de asiento contable no garantiza que la valoración no haya cambiado.') % cost.display_name)
            cost.write({'state': 'draft'})
            cost.message_post(body=_('Costo en Destino restablecido a borrador por %s. No existían asientos ni ajustes asociados a movimientos de inventario.') % self.env.user.display_name)
        return True
