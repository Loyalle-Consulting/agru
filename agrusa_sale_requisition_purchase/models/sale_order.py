# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    agrusa_requisition_released_qty = fields.Float(
        string='Cantidad liberada de requisición', readonly=True, copy=False,
    )

    agrusa_requisition_purchase_line_id = fields.Many2one(
        'purchase.order.line', string='OC generada por requisición',
        readonly=True, copy=False, index=True,
    )

    def _get_qty_procurement(self, *args, **kwargs):
        qty = super()._get_qty_procurement(*args, **kwargs)
        if self.agrusa_supply_origin == 'requisition':
            qty += self.agrusa_requisition_released_qty
        return qty

    def _agrusa_requisition_warehouse(self):
        self.ensure_one()
        warehouses = self.env['stock.warehouse'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('code', '=', 'WH4'),
        ])
        if len(warehouses) != 1:
            raise UserError(_('Requisición: se requiere una única bodega WH4 para %s.') % self.company_id.display_name)
        return warehouses

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if self.agrusa_supply_origin == 'requisition' and not self.display_type:
            warehouse = self._agrusa_requisition_warehouse()
            if not warehouse.delivery_route_id:
                raise UserError(_('Requisición: WH4 no tiene ruta de entrega configurada.'))
            values.update({
                'warehouse_id': warehouse,
                'route_ids': warehouse.delivery_route_id,
            })
        return values

    def _agrusa_factory_pricelist(self):
        self.ensure_one()
        company = self.order_id.company_id
        pricelists = self.env['product.pricelist'].search([
            ('name', 'ilike', 'Euro Fábrica'),
            ('currency_id.name', '=', 'EUR'),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ])
        # Accept unaccented spelling only if no exact accented match exists.
        if not pricelists:
            pricelists = self.env['product.pricelist'].search([
                ('name', 'ilike', 'Euro Fabrica'),
                ('currency_id.name', '=', 'EUR'),
                '|', ('company_id', '=', company.id), ('company_id', '=', False),
            ])
        exact = pricelists.filtered(lambda p: p.name.casefold() in ('euro fábrica', 'euro fabrica'))
        chosen = exact or pricelists
        if len(chosen) != 1:
            raise UserError(_(
                'Requisición: se requiere una única lista de precios «Euro Fábrica» '
                'en EUR para la empresa %s. Se encontraron %s listas compatibles.'
            ) % (company.display_name, len(chosen)))
        return chosen

    def _agrusa_requisition_price(self):
        self.ensure_one()
        if not self.product_id:
            return 0.0
        order = self.order_id
        factory = self._agrusa_factory_pricelist()
        qty = self.product_uom_qty or 1.0
        price_eur = factory._get_product_price(self.product_id, qty, partner=order.partner_id)
        target = order.total_currency_id or order.currency_id
        if target == factory.currency_id:
            return price_eur
        if not target:
            return price_eur
        if order.pricelist_id.currency_id == factory.currency_id and order.total_currency_rate > 0:
            return price_eur * order.total_currency_rate
        if target.name == 'CLP' and order.agrusa_import_fx_rate > 0:
            return price_eur * order.agrusa_import_fx_rate
        date = order.date_order.date() if order.date_order else fields.Date.context_today(order)
        rate = factory.currency_id._get_conversion_rate(factory.currency_id, target, order.company_id, date)
        return price_eur * rate

    def _get_converted_price(self, rate):
        self.ensure_one()
        if self.agrusa_supply_origin == 'requisition':
            return self._agrusa_requisition_price()
        return super()._get_converted_price(rate)

    @api.depends('agrusa_supply_origin', 'product_id', 'product_uom_qty',
                 'order_id.total_currency_id', 'order_id.total_currency_rate',
                 'order_id.agrusa_import_fx_rate', 'order_id.pricelist_id')
    def _compute_agru_price_advice(self):
        super()._compute_agru_price_advice()
        for line in self:
            if line.agrusa_supply_origin != 'requisition' or not line.product_id or line.display_type:
                continue
            suggested = line._agrusa_requisition_price()
            line.agru_suggested_price = suggested
            difference = (line.price_unit - suggested) / suggested * 100 if suggested else 0.0
            line.agru_price_difference_pct = difference
            if not suggested or abs(line.price_unit - suggested) < 0.00001:
                line.agru_price_advice = False
            elif difference < 0:
                line.agru_price_advice = 'ADVERTENCIA: precio inferior al sugerido (%.2f%%)' % abs(difference)
            else:
                line.agru_price_advice = 'AVISO: precio superior al sugerido (+%.2f%%)' % difference

    @api.onchange('agrusa_supply_origin')
    def _onchange_agrusa_requisition_origin(self):
        for line in self:
            if line.display_type or line.agrusa_supply_origin != 'requisition' or not line.product_id:
                continue
            line.with_context(_agru_skip_currency_sync=True).price_unit = line._agrusa_requisition_price()
            line.agru_manual_price = False
            line.agrusa_manual_price_currency_id = False
            line.agrusa_manual_price_base = 0.0

    @api.onchange('product_id', 'product_uom_qty')
    def _onchange_agrusa_requisition_price(self):
        for line in self:
            if line.display_type or line.agrusa_supply_origin != 'requisition' or not line.product_id:
                continue
            if not line.agru_manual_price or not line.agrusa_manual_price_currency_id:
                line.with_context(_agru_skip_currency_sync=True).price_unit = line._agrusa_requisition_price()
                line.agru_manual_price = False
                line.agrusa_manual_price_currency_id = False
                line.agrusa_manual_price_base = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines.filtered(lambda l: l.agrusa_supply_origin == 'requisition' and l.product_id and not l.display_type):
            suggested = line._agrusa_requisition_price()
            # The form often sends an automatically computed price as a manual value.
            if not line.agru_manual_price or abs(line.price_unit - suggested) < 0.00001:
                line.with_context(_agru_skip_currency_sync=True).write({
                    'price_unit': suggested,
                    'agru_manual_price': False,
                    'agrusa_manual_price_currency_id': False,
                    'agrusa_manual_price_base': 0.0,
                })
        return lines


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    agrusa_requisition_purchase_count = fields.Integer(
        string='OC de requisición', compute='_compute_agrusa_requisition_purchase_count'
    )

    def action_open_agrusa_requisition_release(self):
        self.ensure_one()
        if not self.env.user.has_group('agrusa_sale_requisition_purchase.group_requisition_release'):
            raise UserError(_('No tiene autorización para liberar reservas de requisición.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Liberar reserva de Requisición'),
            'res_model': 'agrusa.requisition.release',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _compute_agrusa_requisition_purchase_count(self):
        for order in self:
            order.agrusa_requisition_purchase_count = len(
                order.order_line.mapped('agrusa_requisition_purchase_line_id.order_id')
            )

    def action_view_agrusa_requisition_purchase(self):
        self.ensure_one()
        orders = self.order_line.mapped('agrusa_requisition_purchase_line_id.order_id')
        return {
            'type': 'ir.actions.act_window', 'name': _('OC de requisición'),
            'res_model': 'purchase.order', 'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
        }

    def _agrusa_validate_requisition_lines(self):
        for order in self:
            for line in order.order_line.filtered(lambda l: l.agrusa_supply_origin == 'requisition' and not l.display_type):
                if not line.product_id or line.product_uom_qty <= 0:
                    raise UserError(_('Requisición: producto y cantidad positiva son obligatorios.'))
                line._agrusa_factory_pricelist()
                qty = line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
                seller = line.product_id._select_seller(
                    quantity=qty, date=fields.Date.context_today(line),
                    uom_id=line.product_id.uom_id,
                )
                if not seller:
                    raise UserError(_('Requisición: configure un proveedor válido para %s.') % line.product_id.display_name)

    def _agrusa_create_requisition_purchases(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: l.agrusa_supply_origin == 'requisition' and not l.display_type)
            for line in lines:
                if line.agrusa_requisition_purchase_line_id:
                    continue
                qty = line.product_uom_id._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
                seller = line.product_id._select_seller(
                    quantity=qty, date=fields.Date.context_today(line),
                    uom_id=line.product_id.uom_id,
                )
                if not seller:
                    raise UserError(_('Requisición: falta proveedor de %s.') % line.product_id.display_name)
                currency = seller.currency_id or order.company_id.currency_id
                warehouse = line._agrusa_requisition_warehouse()
                po = self.env['purchase.order'].with_company(order.company_id).create({
                    'picking_type_id': warehouse.in_type_id.id,
                    'partner_id': seller.partner_id.id,
                    'company_id': order.company_id.id,
                    'currency_id': currency.id,
                    'origin': '%s / línea %s' % (order.name, line.id),
                })
                po_line = self.env['purchase.order.line'].with_company(order.company_id).create({
                    'order_id': po.id,
                    'product_id': line.product_id.id,
                    'name': line.product_id.display_name,
                    'product_qty': qty,
                    'product_uom_id': line.product_id.uom_id.id,
                    'price_unit': seller.price,
                    'date_planned': fields.Datetime.now(),
                    'sale_line_id': line.id,
                })
                line.with_context(_agru_skip_currency_sync=True).write({
                    'agrusa_requisition_purchase_line_id': po_line.id,
                })
                order.message_post(body=_('Requisición: OC borrador %s creada para %s (línea %s).') % (
                    po.name, line.product_id.display_name, line.id
                ))

    def action_confirm(self):
        drafts = self.filtered(lambda o: o.state in ('draft', 'sent'))
        drafts._agrusa_validate_requisition_lines()
        result = super().action_confirm()
        # Serialize creation on the sales order to avoid duplicate POs on retries.
        if drafts:
            self.env.cr.execute('SELECT id FROM sale_order WHERE id = ANY(%s) ORDER BY id FOR UPDATE', (drafts.ids,))
            drafts._agrusa_create_requisition_purchases()
        return result
