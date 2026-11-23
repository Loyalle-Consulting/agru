from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare
from markupsafe import Markup, escape


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    agrusa_import_fx_rate = fields.Float(string='Tasa importacion a CLP', digits=(24, 12), default=0.0, copy=False, help='Unidades de CLP por una unidad de moneda de la OC. Se aplica exclusivamente a lineas de importacion cuando la moneda de venta es CLP.')

    @api.onchange('agrusa_import_fx_rate')
    def _onchange_import_fx_rate(self):
        for order in self:
            for line in order.order_line.filtered('agrusa_import_purchase_line_id'):
                if not line.agru_manual_price:
                    line.price_unit = line._agrusa_average_import_price()


    def _apply_total_currency_to_lines(self):
        """Apply conversion to import lines, retaining the seller's manual amount."""
        for order in self:
            # Standard lines keep the existing pricelist-based behavior.
            for line in order.order_line:
                if line.display_type or not order.total_currency_rate:
                    continue
                if not line.agrusa_import_purchase_line_id:
                    target = order.total_currency_id or order.currency_id
                    source = order.pricelist_id.currency_id
                    if line.agru_manual_price:
                        manual_currency = line.agrusa_manual_price_currency_id
                        manual_base = line.agrusa_manual_price_base
                        if not manual_currency:
                            # Legacy/form-created lines often carry a manual flag
                            # even though their price equals the pricelist base.
                            # In that unambiguous case use the pricelist price.
                            original = line.price_unit_original
                            if original and abs(line.price_unit - original) <= max(0.01, abs(original) * 1e-7):
                                manual_currency = source
                                manual_base = original
                                line.agrusa_manual_price_currency_id = source
                                line.agrusa_manual_price_base = original
                            else:
                                # Unknown historical price currency: never guess.
                                continue
                        value = line._agrusa_convert_manual_price(manual_base, manual_currency, target)
                    else:
                        value = line._get_converted_price(order.total_currency_rate)
                    if abs(value - line.price_unit) > 0.00001:
                        line.with_context(_agru_skip_currency_sync=True).price_unit = value
                    continue
                target = order.total_currency_id or order.currency_id
                if line.agru_manual_price:
                    source = line.agrusa_manual_price_currency_id
                    if not source:
                        # Cannot infer the currency of legacy manually marked
                        # prices; do not silently reinterpret or overwrite.
                        line.agrusa_manual_price_currency_id = target
                        line.agrusa_manual_price_base = line.price_unit
                        continue
                    value = line._agrusa_convert_manual_price(
                        line.agrusa_manual_price_base, source, target
                    )
                else:
                    value = line._agrusa_average_import_price()
                if abs(value - line.price_unit) > 0.00001:
                    line.with_context(_agru_skip_currency_sync=True).price_unit = value
                if not line.agru_manual_price:
                    line.agrusa_manual_price_currency_id = False
                    line.agrusa_manual_price_base = 0.0

    def action_confirm(self):
        # Serializa confirmaciones concurrentes que compiten por una misma linea de compra.
        lines = self.order_line.filtered(lambda l: l.agrusa_import_purchase_line_id)
        po_ids = sorted(set(lines.mapped('agrusa_import_purchase_line_id').ids))
        if po_ids:
            self.env.cr.execute('SELECT id FROM purchase_order_line WHERE id = ANY(%s) ORDER BY id FOR UPDATE', (po_ids,))
            SaleLine = self.env['sale.order.line'].sudo()
            for po_line in self.env['purchase.order.line'].browse(po_ids):
                if po_line.order_id.state not in ('purchase', 'done') or not po_line.order_id.agrusa_is_import:
                    raise UserError(_('La OC %s debe estar confirmada y marcada como importacion.') % po_line.order_id.name)
                committed = SaleLine.search([
                    ('agrusa_import_purchase_line_id', '=', po_line.id),
                    ('order_id.state', 'in', ['sale', 'done']),
                ])
                pending = lines.filtered(lambda l: l.agrusa_import_purchase_line_id == po_line and l.order_id.state in ('draft', 'sent'))
                qty = sum(l.product_uom_id._compute_quantity(l.product_uom_qty, po_line.product_uom_id) for l in committed | pending)
                if float_compare(qty, po_line.product_qty, precision_rounding=po_line.product_uom_id.rounding) > 0:
                    raise UserError(_('Importacion %s / %s: se solicitan %.3f unidades y solo existen %.3f compradas.') % (po_line.order_id.name, po_line.product_id.display_name, qty, po_line.product_qty))
        return super().action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    agrusa_import_purchase_line_id = fields.Many2one(
        'purchase.order.line', string='Origen importacion (linea OC)', copy=False,
        domain="[('product_id', '=', product_id), ('order_id.agrusa_is_import', '=', True), ('order_id.state', 'in', ['purchase', 'done']), ('agrusa_import_selectable', '=', True)]",
    )
    agrusa_import_factor_snapshot = fields.Float(string='Factor aplicado', copy=False, digits=(16, 6), readonly=True)
    agrusa_import_rate_snapshot = fields.Float(string='Tasa aplicada', copy=False, digits=(24, 12), readonly=True)
    agrusa_import_price_locked = fields.Boolean(string='Precio importacion confirmado', copy=False, readonly=True)
    agrusa_import_available_qty = fields.Float(related='agrusa_import_purchase_line_id.agrusa_available_qty', string='Saldo OC', readonly=True)

    agrusa_oc_factor_price = fields.Float(string='Precio OC con factor', compute='_compute_agrusa_commercial_references', digits='Product Price')
    agrusa_average_factor_price = fields.Float(string='Promedio importaciones', compute='_compute_agrusa_commercial_references', digits='Product Price')
    agrusa_general_average_price = fields.Float(
        string='PROMEDIO GENERAL', compute='_compute_agrusa_commercial_references',
        digits='Product Price', help='Promedio ponderado de importaciones pendientes y existencias fisicas en Bodega Principal, expresado en la moneda de la cotizacion.'
    )

    agru_manual_price = fields.Boolean(string='Precio modificado manualmente', copy=False, default=False)
    agrusa_manual_price_currency_id = fields.Many2one(
        'res.currency', string='Moneda de referencia del precio manual', copy=False
    )
    agrusa_manual_price_base = fields.Float(
        string='Importe original del precio manual', digits=(24, 12), copy=False
    )

    def _agrusa_convert_manual_price(self, amount, source, target):
        """Convert the manual reference without compounding prior conversions."""
        self.ensure_one()
        if not source or not target or source == target:
            return amount
        order = self.order_id
        pricelist_currency = order.pricelist_id.currency_id
        if source == pricelist_currency and order.total_currency_rate > 0:
            return amount * order.total_currency_rate
        date = order.date_order.date() if order.date_order else fields.Date.context_today(order)
        rate = source._get_conversion_rate(source, target, order.company_id, date)
        return amount * rate
    agru_suggested_price = fields.Float(string='Precio sugerido AGRU', compute='_compute_agru_price_advice', digits='Product Price')
    agru_price_difference_pct = fields.Float(string='Diferencia %', compute='_compute_agru_price_advice', digits=(16, 2))
    agru_price_advice = fields.Char(string='Aviso comercial', compute='_compute_agru_price_advice')

    @api.depends('price_unit', 'product_id', 'product_uom_qty', 'agrusa_import_purchase_line_id',
                 'order_id.pricelist_id', 'order_id.total_currency_rate', 'order_id.total_currency_id',
                 'order_id.agrusa_import_fx_rate', 'agrusa_import_purchase_line_id.price_unit',
                 'agrusa_import_purchase_line_id.agrusa_import_factor')
    def _compute_agru_price_advice(self):
        for line in self:
            suggested = 0.0
            if line.product_id and not line.display_type:
                if line.agrusa_import_purchase_line_id:
                    suggested = line._agrusa_average_import_price()
                elif line.order_id.total_currency_rate:
                    suggested = line._get_converted_price(line.order_id.total_currency_rate)
                else:
                    suggested = line._get_reliable_pricelist_price()
            line.agru_suggested_price = suggested
            difference = (line.price_unit - suggested) / suggested * 100 if suggested else 0.0
            line.agru_price_difference_pct = difference
            if not suggested or abs(line.price_unit - suggested) < 0.00001:
                line.agru_price_advice = False
            elif difference < 0:
                line.agru_price_advice = 'ADVERTENCIA: precio inferior al sugerido (%.2f%%)' % abs(difference)
            else:
                line.agru_price_advice = 'AVISO: precio superior al sugerido (+%.2f%%)' % difference

    @api.depends('product_id', 'company_id', 'agrusa_import_purchase_line_id',
                 'order_id.currency_id', 'order_id.total_currency_id',
                 'order_id.total_currency_rate', 'order_id.agrusa_import_fx_rate',
                 'agrusa_import_purchase_line_id.price_unit',
                 'agrusa_import_purchase_line_id.agrusa_import_factor')
    def _compute_agrusa_commercial_references(self):
        for line in self:
            if line.agrusa_import_purchase_line_id and line.product_id:
                line.agrusa_oc_factor_price = line._agrusa_import_price()
                line.agrusa_average_factor_price = line._agrusa_average_import_price()
            else:
                line.agrusa_oc_factor_price = 0.0
                line.agrusa_average_factor_price = 0.0
            line.agrusa_general_average_price = (
                line._agrusa_general_average_price() if line.product_id and not line.display_type else 0.0
            )

    def _agrusa_general_average_price(self):
        """Weighted import commercial reference plus physical stock cost in main WH.

        Import portion uses the SAME quantities and price conversion as the existing
        import average; warehouse portion uses on-hand quants and the current
        company-dependent product cost. This is an informational reference only.
        """
        self.ensure_one()
        product = self.product_id
        order = self.order_id
        if not product or not order.company_id:
            return 0.0
        company = order.company_id
        target = order.total_currency_id or order.currency_id
        numerator = denominator = 0.0

        purchases = self.env['purchase.order.line'].search([
            ('product_id', '=', product.id),
            ('company_id', '=', company.id),
            ('order_id.agrusa_is_import', '=', True),
            ('order_id.state', 'in', ('purchase', 'done')),
        ])
        for po in purchases:
            pending = max(0.0, po.product_qty - po.qty_received)
            if not pending:
                continue
            qty = po.product_uom_id._compute_quantity(pending, product.uom_id)
            numerator += qty * self._agrusa_price_for_purchase_line(po)
            denominator += qty

        # Only physical on-hand quantities at the company's MAIN warehouse.
        # Do not include transit, consignments, requisitions or supplier stock.
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', company.id), ('code', '=', 'WH')
        ], limit=1)
        if warehouse and warehouse.lot_stock_id:
            quants = self.env['stock.quant'].sudo().with_company(company).search([
                ('product_id', '=', product.id),
                ('company_id', '=', company.id),
                ('location_id', 'child_of', warehouse.lot_stock_id.id),
                ('location_id.usage', '=', 'internal'),
                ('owner_id', '=', False),
            ])
            physical_qty = max(0.0, sum(quants.mapped('quantity')))
            if physical_qty:
                # Standard price is the current company cost, not a per-lot
                # historical cost; convert it to the quote currency.
                cost = product.with_company(company).standard_price
                if target and company.currency_id != target:
                    date = order.date_order.date() if order.date_order else fields.Date.context_today(order)
                    cost = company.currency_id._convert(cost, target, company, date)
                numerator += physical_qty * cost
                denominator += physical_qty
        return numerator / denominator if denominator else 0.0

    def _agrusa_average_import_price(self):
        """Promedio comercial ponderado por cantidades pendientes de recibir.

        Las reservas comerciales NO modifican el peso de cada OC.
        La disponibilidad para comprometer ventas se controla por separado.
        """
        self.ensure_one()
        selected = self.agrusa_import_purchase_line_id
        if not selected or not self.product_id:
            return 0.0
        purchases = self.env['purchase.order.line'].search([
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.order_id.company_id.id),
            ('order_id.agrusa_is_import', '=', True),
            ('order_id.state', 'in', ('purchase', 'done')),
        ])
        numerator = denominator = 0.0
        for po in purchases:
            pending_receipt = max(0.0, po.product_qty - po.qty_received)
            if pending_receipt <= 0:
                continue
            # Normalizar cantidades de distintas UoM a la unidad del producto.
            qty = po.product_uom_id._compute_quantity(pending_receipt, self.product_id.uom_id)
            numerator += qty * self._agrusa_price_for_purchase_line(po)
            denominator += qty
        return numerator / denominator if denominator else self._agrusa_import_price()

    @api.onchange('price_unit')
    def _onchange_agru_manual_price(self):
        for line in self:
            if line.product_id and not line.display_type:
                if not line.env.context.get('_agru_skip_currency_sync'):
                    line.agru_manual_price = True
                    line.agrusa_manual_price_currency_id = (
                        line.order_id.total_currency_id or line.order_id.currency_id
                    )
                    line.agrusa_manual_price_base = line.price_unit

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'price_unit' in vals and 'agru_manual_price' not in vals:
                # Precio aportado por el formulario o integración: no recalcularlo
                # silenciosamente. El valor sugerido se conserva por separado.
                vals['agru_manual_price'] = True
        lines = super().create(vals_list)
        for line in lines.filtered('agrusa_import_purchase_line_id'):
            if line.agru_manual_price and not line.agrusa_manual_price_currency_id:
                suggested = line._agrusa_average_import_price()
                if abs(line.price_unit - suggested) < 0.00001:
                    line.with_context(_agru_skip_currency_sync=True).write({
                        'agru_manual_price': False,
                    })
                else:
                    line.with_context(_agru_skip_currency_sync=True).write({
                        'agrusa_manual_price_currency_id': (
                            line.order_id.total_currency_id or line.order_id.currency_id
                        ).id,
                        'agrusa_manual_price_base': line.price_unit,
                    })
        for line in lines.filtered(lambda l: not l.display_type and l.product_id and not l.agrusa_import_purchase_line_id):
            if line.agru_manual_price and not line.agrusa_manual_price_currency_id:
                original = line.price_unit_original
                if original and abs(line.price_unit - original) <= max(0.01, abs(original) * 1e-7):
                    line.with_context(_agru_skip_currency_sync=True).write({
                        'agrusa_manual_price_currency_id': line.order_id.pricelist_id.currency_id.id,
                        'agrusa_manual_price_base': original,
                    })
                else:
                    # New explicit price, currency is the quotation currency.
                    line.with_context(_agru_skip_currency_sync=True).write({
                        'agrusa_manual_price_currency_id': (line.order_id.total_currency_id or line.order_id.currency_id).id,
                        'agrusa_manual_price_base': line.price_unit,
                    })
        return lines


    @api.constrains('agrusa_import_purchase_line_id', 'product_id', 'company_id')
    def _check_import_origin(self):
        for line in self:
            po = line.agrusa_import_purchase_line_id
            if po and (po.product_id != line.product_id or po.company_id != line.company_id):
                raise ValidationError(_('La linea de importacion debe corresponder al mismo producto y compania.'))

    def _agrusa_import_price(self):
        self.ensure_one()
        return self._agrusa_price_for_purchase_line(self.agrusa_import_purchase_line_id)

    def _agrusa_price_for_purchase_line(self, po):
        self.ensure_one()
        if not po:
            return 0.0
        order = self.order_id
        source = po.currency_id
        target = order.total_currency_id or order.currency_id
        if not source or not target:
            return 0.0
        base = po.price_unit * po.agrusa_import_factor
        if source == target:
            return base
        # La tasa editable existente representa lista de precios -> moneda final.
        # Solo es aplicable directamente cuando la lista coincide con moneda de la OC.
        reference = order.pricelist_id.currency_id
        if target.name == 'CLP' and order.agrusa_import_fx_rate > 0:
            return base * order.agrusa_import_fx_rate
        # Si la moneda de OC coincide con la lista, usar la tasa comercial existente.
        if source == reference and order.total_currency_rate > 0:
            return base * order.total_currency_rate
        # Fallback: conversion oficial, solo cuando no se definio tasa comercial directa.
        date = order.date_order.date() if order.date_order else fields.Date.context_today(order)
        rate = source._get_conversion_rate(source, target, order.company_id, date)
        return base * rate

    def _get_converted_price(self, rate):
        self.ensure_one()
        if self.agrusa_import_purchase_line_id:
            return self._agrusa_average_import_price()
        return super()._get_converted_price(rate)

    @api.onchange('agrusa_import_purchase_line_id', 'product_id')
    def _onchange_import_origin(self):
        for line in self:
            po = line.agrusa_import_purchase_line_id
            if po and po.product_id != line.product_id:
                line.agrusa_import_purchase_line_id = False
                continue
            if po:
                line.price_unit = line._agrusa_average_import_price()
                line.agru_manual_price = False

    def write(self, vals):
        if 'agrusa_import_purchase_line_id' in vals and any(l.order_id.state not in ('draft', 'sent') for l in self):
            raise UserError(_('No se puede cambiar la importacion de una venta confirmada.'))
        audit = {}
        if 'price_unit' in vals and not self.env.context.get('_agru_skip_currency_sync'):
            for line in self:
                if line.product_id and not line.display_type and line.order_id.state in ('draft', 'sent'):
                    new_price = float(vals['price_unit'])
                    if abs(line.price_unit - new_price) > 0.00001:
                        audit[line.id] = (line.order_id, line.product_id.display_name,
                                          line.agrusa_import_purchase_line_id.order_id.name if line.agrusa_import_purchase_line_id else 'Bodega principal / lista de precios',
                                          line.price_unit, line.agru_suggested_price,
                                          line.order_id.currency_id.name,
                                          line.agrusa_oc_factor_price,
                                          line.agrusa_average_factor_price)
            vals = dict(vals, agru_manual_price=True)
        result = super().write(vals)
        if 'price_unit' in vals and not self.env.context.get('_agru_skip_currency_sync'):
            for line in self.filtered(lambda l: not l.display_type and l.product_id):
                line.with_context(_agru_skip_currency_sync=True).write({
                    'agrusa_manual_price_currency_id': (
                        line.order_id.total_currency_id or line.order_id.currency_id
                    ).id,
                    'agrusa_manual_price_base': line.price_unit,
                })
        for line in self:
            if line.id not in audit:
                continue
            order, product, origin, old, suggested, currency, oc_price, average_price = audit[line.id]
            new = line.price_unit
            diff = (new - suggested) / suggested * 100 if suggested else 0.0
            body = Markup('<b>Auditoría comercial AGRU – modificación de precio</b><br/>Producto: %s<br/>Origen: %s<br/>Precio sugerido: %.4f %s<br/>Precio OC con factor: %.4f %s<br/>Promedio importaciones: %.4f %s<br/>Precio anterior: %.4f %s<br/>Nuevo precio: %.4f %s<br/>Diferencia respecto al sugerido: %+.2f%%<br/>Usuario: %s') % (
                escape(product), escape(origin), suggested, escape(currency),
                oc_price, escape(currency), average_price, escape(currency), old, escape(currency),
                new, escape(currency), diff, escape(self.env.user.display_name))
            order.message_post(body=body, subtype_xmlid='mail.mt_note')
        return result
