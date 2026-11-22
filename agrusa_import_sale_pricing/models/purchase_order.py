from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    agrusa_is_import = fields.Boolean(string='Importacion comercial', default=False, copy=True)
    agrusa_import_factor = fields.Float(string='Factor comercial general', default=1.0, digits=(16, 6))

    @api.constrains('agrusa_import_factor')
    def _check_factor(self):
        for order in self:
            if order.agrusa_import_factor <= 0:
                raise ValidationError(_('El factor comercial debe ser mayor que cero.'))


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    agrusa_import_factor = fields.Float(string='Factor comercial', default=1.0, digits=(16, 6))
    agrusa_import_selector_label = fields.Char(compute='_compute_import_selector_label')

    @api.depends('order_id.name', 'date_planned', 'product_id', 'price_unit',
                 'agrusa_import_factor', 'currency_id', 'product_qty',
                 'qty_received', 'order_id.state')
    def _agrusa_selector_average(self):
        """Promedio ponderado por saldo comercial en moneda de la OC seleccionada.

        Para monedas diferentes se aplica conversión contable oficial. El valor
        de la columna de la venta prevalece si la cotización usa una tasa manual.
        """
        self.ensure_one()
        if not self.product_id or not self.currency_id:
            return 0.0
        candidates = self.env['purchase.order.line'].search([
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.company_id.id),
            ('order_id.agrusa_is_import', '=', True),
            ('order_id.state', 'in', ('purchase', 'done')),
        ])
        total = weight = 0.0
        for candidate in candidates:
            available = candidate.agrusa_available_qty
            if available <= 0:
                continue
            qty = candidate.product_uom_id._compute_quantity(
                available, self.product_id.uom_id)
            price = candidate.price_unit * candidate.agrusa_import_factor
            if candidate.currency_id != self.currency_id:
                date = fields.Date.context_today(self)
                price = candidate.currency_id._convert(
                    price, self.currency_id, self.company_id, date)
            total += qty * price
            weight += qty
        return total / weight if weight else self.agrusa_import_base_price

    def _agrusa_selector_general_average(self):
        """Promedio importaciones pendientes + stock fisico WH, en moneda OC.

        Replica la referencia comercial de la columna PROMEDIO GENERAL,
        sin modificar precios, reservas ni aprovisionamientos.
        """
        self.ensure_one()
        if not self.product_id or not self.currency_id or not self.company_id:
            return 0.0
        product = self.product_id
        company = self.company_id
        target = self.currency_id
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
            price = po.price_unit * po.agrusa_import_factor
            if po.currency_id != target:
                price = po.currency_id._convert(
                    price, target, company, fields.Date.context_today(self))
            numerator += qty * price
            denominator += qty

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
                cost = product.with_company(company).standard_price
                if company.currency_id != target:
                    cost = company.currency_id._convert(
                        cost, target, company, fields.Date.context_today(self))
                numerator += physical_qty * cost
                denominator += physical_qty
        return numerator / denominator if denominator else 0.0

    def _compute_import_selector_label(self):
        for line in self:
            eta = fields.Date.to_string(line.date_planned.date()) if line.date_planned else '-'
            average = line._agrusa_selector_average() if line.id else 0.0
            general_average = line._agrusa_selector_general_average() if line.id else 0.0
            line.agrusa_import_selector_label = (
                '%s | ETA %s | %s | saldo comercial %.2f | por recibir %.2f '
                '| precio OC %.2f %s | promedio importaciones %.2f %s | PROMEDIO GENERAL %.2f %s'
                % (line.order_id.name or '-', eta, line.product_id.display_name or '-',
                   line.agrusa_available_qty,
                   max(0.0, line.product_qty - line.qty_received),
                   line.agrusa_import_base_price, line.currency_id.name or '',
                   average, line.currency_id.name or '',
                   general_average, line.currency_id.name or '')
            )

    @api.depends_context('agrusa_import_selector')
    def _compute_display_name(self):
        if not self.env.context.get('agrusa_import_selector'):
            return super()._compute_display_name()
        for line in self:
            line.display_name = line.agrusa_import_selector_label

    agrusa_import_base_price = fields.Monetary(string='Precio comercial en moneda OC', compute='_compute_import_base_price', currency_field='currency_id')
    agrusa_reserved_qty = fields.Float(string='Comprometido comercial', compute='_compute_import_reserved', digits='Product Unit of Measure')
    agrusa_available_qty = fields.Float(string='Saldo comercial', compute='_compute_import_reserved', digits='Product Unit of Measure')

    @api.onchange('order_id')
    def _onchange_import_factor(self):
        for line in self:
            if line.order_id:
                line.agrusa_import_factor = line.order_id.agrusa_import_factor

    @api.depends('price_unit', 'agrusa_import_factor')
    def _compute_import_base_price(self):
        for line in self:
            line.agrusa_import_base_price = line.price_unit * line.agrusa_import_factor

    @api.depends('product_qty', 'order_id.state')
    def _compute_import_reserved(self):
        SaleLine = self.env['sale.order.line'].sudo()
        for line in self:
            sales = SaleLine.search([
                ('agrusa_import_purchase_line_id', '=', line.id),
                ('order_id.state', 'in', ['sale', 'done']),
            ]) if line.id else SaleLine.browse()
            reserved = 0.0
            for sale in sales:
                qty = sale.product_uom_id._compute_quantity(sale.product_uom_qty, line.product_uom_id)
                reserved += qty
            line.agrusa_reserved_qty = reserved
            line.agrusa_available_qty = max(0.0, line.product_qty - reserved)

    @api.constrains('agrusa_import_factor')
    def _check_import_factor(self):
        for line in self:
            if line.agrusa_import_factor <= 0:
                raise ValidationError(_('El factor comercial de cada linea debe ser mayor que cero.'))
