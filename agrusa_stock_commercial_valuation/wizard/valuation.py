from collections import defaultdict
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AgrusaCommercialValuationWizard(models.TransientModel):
    _name = 'agrusa.commercial.valuation.wizard'
    _description = 'AGRUSA - Consulta valorizacion comercial'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    valuation_date = fields.Date(string='Fecha tipo de cambio', required=True, default=fields.Date.context_today)
    warehouse_id = fields.Many2one('stock.warehouse', string='Bodega (opcional)', domain="[('company_id', '=', company_id)]")
    product_id = fields.Many2one('product.product', string='Producto (opcional)')
    line_ids = fields.One2many('agrusa.commercial.valuation.line', 'wizard_id', string='Valorizacion', readonly=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id')
    total_physical_clp = fields.Monetary(compute='_compute_totals', currency_field='company_currency_id')
    total_transit_clp = fields.Monetary(compute='_compute_totals', currency_field='company_currency_id')
    total_pending_clp = fields.Monetary(compute='_compute_totals', currency_field='company_currency_id')
    total_free_clp = fields.Monetary(compute='_compute_totals', currency_field='company_currency_id')

    @api.depends('line_ids.physical_value_clp', 'line_ids.transit_value_clp', 'line_ids.pending_value_clp', 'line_ids.free_value_clp')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_physical_clp = sum(wizard.line_ids.mapped('physical_value_clp'))
            wizard.total_transit_clp = sum(wizard.line_ids.mapped('transit_value_clp'))
            wizard.total_pending_clp = sum(wizard.line_ids.mapped('pending_value_clp'))
            wizard.total_free_clp = sum(wizard.line_ids.mapped('free_value_clp'))

    def action_generate(self):
        self.ensure_one()
        if self.warehouse_id and self.warehouse_id.company_id != self.company_id:
            raise UserError(_('La bodega debe pertenecer a la empresa seleccionada.'))
        self.line_ids.unlink()
        domain = [('order_id.company_id', '=', self.company_id.id),
                  ('order_id.state', 'in', ['purchase', 'done']),
                  ('order_id.agrusa_is_import', '=', True),
                  ('product_id', '!=', False)]
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        purchase_lines = self.env['purchase.order.line'].search(domain, order='order_id, id')
        if not purchase_lines:
            return self._action_open_lines()

        po_ids = purchase_lines.ids
        receipt_lines = self.env['stock.move.line'].search([
            ('move_id.purchase_line_id', 'in', po_ids),
            ('move_id.state', '=', 'done'),
            ('lot_id', '!=', False),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'supplier'),
            ('location_dest_id.usage', '=', 'internal'),
        ])
        lots_by_po = defaultdict(set)
        po_by_lot = defaultdict(set)
        for ml in receipt_lines:
            po_id = ml.move_id.purchase_line_id.id
            lots_by_po[po_id].add(ml.lot_id.id)
            po_by_lot[ml.lot_id.id].add(po_id)
        # Any lot received under another PO, including outside the current report, is ambiguous.
        all_lots = list(po_by_lot)
        if all_lots:
            other_receipts = self.env['stock.move.line'].search([
                ('lot_id', 'in', all_lots), ('move_id.state', '=', 'done'),
                ('move_id.purchase_line_id', '!=', False), ('quantity', '>', 0),
                ('location_id.usage', '=', 'supplier'),
                ('location_dest_id.usage', '=', 'internal'),
            ])
            for ml in other_receipts:
                po_by_lot[ml.lot_id.id].add(ml.move_id.purchase_line_id.id)
        ambiguous = {lot for lot, origins in po_by_lot.items() if len(origins) > 1}
        safe_lots = set(all_lots) - ambiguous

        quants = self.env['stock.quant'].search([
            ('lot_id', 'in', list(safe_lots) or [0]),
            ('company_id', '=', self.company_id.id),
            ('location_id.usage', '=', 'internal'),
        ])
        if self.warehouse_id:
            location_ids = set(self.env['stock.location'].search([
                ('id', 'child_of', self.warehouse_id.view_location_id.id),
                ('usage', '=', 'internal'),
            ]).ids)
            quants = quants.filtered(lambda q: q.location_id.id in location_ids)
        stock_by_lot = defaultdict(float)
        reserved_by_lot = defaultdict(float)
        for q in quants:
            stock_by_lot[q.lot_id.id] += q.quantity
            reserved_by_lot[q.lot_id.id] += q.reserved_quantity

        sale_lines = self.env['sale.order.line'].search([
            ('agrusa_import_purchase_line_id', 'in', po_ids),
            ('order_id.state', 'in', ['sale', 'done']),
        ])
        pending_by_po = defaultdict(float)
        for sl in sale_lines:
            po = sl.agrusa_import_purchase_line_id
            # qty_delivered is Odoo's net delivered quantity, including returns.
            pending = max(sl.product_uom_qty - sl.qty_delivered, 0.0)
            pending_by_po[po.id] += sl.product_uom_id._compute_quantity(pending, po.product_uom_id)

        vals = []
        for po in purchase_lines:
            po_lots = lots_by_po[po.id] & safe_lots
            # Quants are in product UoM; purchase line quantities are in purchase UoM.
            physical_product_uom = sum(max(stock_by_lot[lot], 0.0) for lot in po_lots)
            reserved_product_uom = sum(max(reserved_by_lot[lot], 0.0) for lot in po_lots)
            physical = po.product_id.uom_id._compute_quantity(physical_product_uom, po.product_uom_id)
            reserved = po.product_id.uom_id._compute_quantity(reserved_product_uom, po.product_uom_id)
            transit = max(po.product_qty - po.qty_received, 0.0)
            pending = pending_by_po[po.id]
            free = max(physical + transit - pending, 0.0)
            unit_price = po.agrusa_import_base_price
            currency = po.currency_id or po.order_id.currency_id
            rate = currency._convert(1.0, self.company_id.currency_id, self.company_id, self.valuation_date, round=False)
            vals.append({
                'wizard_id': self.id,
                'purchase_line_id': po.id,
                'product_id': po.product_id.id,
                'warehouse_id': self.warehouse_id.id or False,
                'currency_id': currency.id,
                'company_currency_id': self.company_id.currency_id.id,
                'unit_price': unit_price,
                'fx_rate': rate,
                'ordered_qty': po.product_qty,
                'received_qty': po.qty_received,
                'physical_qty': physical,
                'physical_reserved_qty': reserved,
                'transit_qty': transit,
                'pending_delivery_qty': pending,
                'free_qty': free,
                'ambiguous_lot_count': len(lots_by_po[po.id] & ambiguous),
                'physical_value': physical * unit_price,
                'transit_value': transit * unit_price,
                'pending_value': pending * unit_price,
                'free_value': free * unit_price,
                'physical_value_clp': physical * unit_price * rate,
                'transit_value_clp': transit * unit_price * rate,
                'pending_value_clp': pending * unit_price * rate,
                'free_value_clp': free * unit_price * rate,
            })
        self.env['agrusa.commercial.valuation.line'].create(vals)
        return self._action_open_lines()

    def _action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('AGRUSA - Valorizacion comercial'),
            'res_model': 'agrusa.commercial.valuation.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class AgrusaCommercialValuationLine(models.TransientModel):
    _name = 'agrusa.commercial.valuation.line'
    _description = 'AGRUSA - Linea valorizacion comercial'
    _order = 'purchase_line_id, id'

    wizard_id = fields.Many2one('agrusa.commercial.valuation.wizard', required=True, ondelete='cascade')
    purchase_line_id = fields.Many2one('purchase.order.line', string='Linea OC', readonly=True)
    purchase_order_id = fields.Many2one(related='purchase_line_id.order_id', string='OC')
    product_id = fields.Many2one('product.product', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', readonly=True)
    eta = fields.Datetime(related='purchase_line_id.date_planned', string='ETA')
    currency_id = fields.Many2one('res.currency', readonly=True)
    company_currency_id = fields.Many2one('res.currency', readonly=True)
    unit_price = fields.Monetary(currency_field='currency_id', readonly=True)
    fx_rate = fields.Float(string='Tasa a CLP', digits=(18, 8), readonly=True)
    ordered_qty = fields.Float(readonly=True)
    received_qty = fields.Float(readonly=True)
    physical_qty = fields.Float(readonly=True)
    physical_reserved_qty = fields.Float(readonly=True)
    transit_qty = fields.Float(readonly=True)
    pending_delivery_qty = fields.Float(readonly=True)
    free_qty = fields.Float(readonly=True)
    ambiguous_lot_count = fields.Integer(readonly=True)
    physical_value = fields.Monetary(currency_field='currency_id', readonly=True)
    transit_value = fields.Monetary(currency_field='currency_id', readonly=True)
    pending_value = fields.Monetary(currency_field='currency_id', readonly=True)
    free_value = fields.Monetary(currency_field='currency_id', readonly=True)
    physical_value_clp = fields.Monetary(currency_field='company_currency_id', readonly=True)
    transit_value_clp = fields.Monetary(currency_field='company_currency_id', readonly=True)
    pending_value_clp = fields.Monetary(currency_field='company_currency_id', readonly=True)
    free_value_clp = fields.Monetary(currency_field='company_currency_id', readonly=True)
