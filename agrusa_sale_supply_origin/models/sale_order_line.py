from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    agrusa_supply_origin = fields.Selection(
        [('warehouse', 'Bodega principal'),
         ('transit', 'Tránsito / importación'),
         ('requisition', 'Requisición (pendiente de abastecer)')],
        string='Origen de abastecimiento',
        default='warehouse',
        required=True,
        copy=True,
        index=True,
        help='La requisición genera una OC en borrador al confirmar la venta, mediante el módulo de compras AGRUSA.',
    )

    def _agrusa_transit_warehouse(self):
        """Resolve the designated import/transit warehouse for this company."""
        self.ensure_one()
        warehouses = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('code', '=', 'WH2'),
        ])
        if len(warehouses) != 1:
            raise UserError(_(
                'Tránsito: se requiere una única bodega WH2 para %s.'
            ) % self.company_id.display_name)
        return warehouses

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if self.agrusa_supply_origin == 'transit' and not self.display_type:
            warehouse = self._agrusa_transit_warehouse()
            if not warehouse.delivery_route_id:
                raise UserError(_(
                    'Tránsito: la bodega WH2 no tiene ruta de entrega configurada.'
                ))
            values.update({
                'warehouse_id': warehouse,
                'route_ids': warehouse.delivery_route_id,
            })
        return values

    @api.onchange('agrusa_supply_origin')
    def _onchange_agrusa_supply_origin(self):
        for line in self:
            if line.display_type:
                continue
            if line.agrusa_supply_origin != 'transit':
                line.agrusa_import_purchase_line_id = False
                if not line.agru_manual_price and line.product_id:
                    line.price_unit = (line._get_converted_price(line.order_id.total_currency_rate)
                                       if line.order_id.total_currency_rate
                                       else line._get_reliable_pricelist_price())
            elif line.agrusa_import_purchase_line_id and not line.agru_manual_price:
                line.price_unit = line._agrusa_average_import_price()

    @api.onchange('agrusa_import_purchase_line_id')
    def _onchange_agrusa_origin_from_po(self):
        for line in self:
            if line.agrusa_import_purchase_line_id:
                line.agrusa_supply_origin = 'transit'

    @api.model_create_multi
    def create(self, vals_list):
        normalized = []
        for vals in vals_list:
            vals = dict(vals)
            if 'agrusa_supply_origin' not in vals and vals.get('agrusa_import_purchase_line_id'):
                vals['agrusa_supply_origin'] = 'transit'
            if vals.get('agrusa_supply_origin') in ('warehouse', 'requisition'):
                vals['agrusa_import_purchase_line_id'] = False
            normalized.append(vals)
        return super().create(normalized)

    def write(self, vals):
        if 'agrusa_supply_origin' in vals and any(
            not line.display_type and line.order_id.state not in ('draft', 'sent') for line in self
        ):
            raise UserError(_('No se puede cambiar el origen de abastecimiento de una venta confirmada.'))
        vals = dict(vals)
        if vals.get('agrusa_supply_origin') in ('warehouse', 'requisition'):
            vals['agrusa_import_purchase_line_id'] = False
        if vals.get('agrusa_import_purchase_line_id') and 'agrusa_supply_origin' not in vals:
            vals['agrusa_supply_origin'] = 'transit'
        return super().write(vals)

    @api.constrains('agrusa_supply_origin', 'agrusa_import_purchase_line_id')
    def _check_agrusa_supply_origin(self):
        for line in self:
            if line.display_type:
                continue
            if line.agrusa_supply_origin != 'transit' and line.agrusa_import_purchase_line_id:
                raise ValidationError(_('Solo el origen Tránsito permite asociar una OC de importación.'))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        for order in self:
            for line in order.order_line.filtered(lambda l: not l.display_type):
                if line.agrusa_supply_origin == 'transit' and not line.agrusa_import_purchase_line_id:
                    raise UserError(_(
                        'La línea %s tiene origen Tránsito, pero no tiene una OC de importación seleccionada.'
                    ) % line.product_id.display_name)
        return super().action_confirm()
