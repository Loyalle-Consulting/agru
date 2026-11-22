from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = 'stock.move'

    agrusa_import_purchase_line_id = fields.Many2one(
        'purchase.order.line', string='Origen importacion AGRUSA',
        related='sale_line_id.agrusa_import_purchase_line_id',
        store=True, readonly=True, index=True,
    )

    def _agrusa_allowed_import_lots(self):
        """Only unambiguously sourced lots from completed receipts are eligible.

        A shared lot across multiple purchase lines is deliberately excluded:
        Odoo quants are not segregated by purchase order, so lot-only reservation
        cannot guarantee provenance in that case.
        """
        self.ensure_one()
        po_line = self.agrusa_import_purchase_line_id
        Lot = self.env['stock.lot']
        if not po_line:
            return Lot.browse()
        incoming = po_line.move_ids.filtered(lambda m: m.state == 'done')
        lots = incoming.move_line_ids.filtered(
            lambda ml: ml.lot_id and ml.quantity > 0
        ).mapped('lot_id')
        if not lots:
            return Lot.browse()
        # Exclude lots also received under another purchase line. This is
        # conservative and protects the promised provenance guarantee.
        other_receipts = self.env['stock.move.line'].sudo().search([
            ('lot_id', 'in', lots.ids),
            ('move_id.state', '=', 'done'),
            ('move_id.purchase_line_id', '!=', False),
            ('move_id.purchase_line_id', '!=', po_line.id),
            ('quantity', '>', 0),
        ])
        ambiguous = other_receipts.mapped('lot_id')
        return lots - ambiguous

    def _update_reserved_quantity(self, need, location_id, lot_id=None,
                                  package_id=None, owner_id=None, strict=True):
        self.ensure_one()
        if not self.agrusa_import_purchase_line_id or self.location_dest_id.usage != 'customer':
            return super()._update_reserved_quantity(
                need, location_id, lot_id, package_id, owner_id, strict
            )
        allowed = self._agrusa_allowed_import_lots()
        if lot_id:
            if lot_id not in allowed:
                return 0.0
            return super()._update_reserved_quantity(
                need, location_id, lot_id, package_id, owner_id, True
            )
        taken = 0.0
        for lot in allowed:
            remaining = need - taken
            if float_compare(remaining, 0, precision_rounding=self.product_id.uom_id.rounding) <= 0:
                break
            taken += super()._update_reserved_quantity(
                remaining, location_id, lot, package_id, owner_id, True
            )
        return taken

    def _update_reserved_quantity_vals(self, need, location_id, lot_id=None,
                                       package_id=None, owner_id=None, strict=True):
        self.ensure_one()
        if self.agrusa_import_purchase_line_id and self.location_dest_id.usage == 'customer':
            allowed = self._agrusa_allowed_import_lots()
            if not lot_id or lot_id not in allowed:
                return [], 0.0
        return super()._update_reserved_quantity_vals(
            need, location_id, lot_id, package_id, owner_id, strict
        )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    
    def button_validate(self):
        for picking in self.filtered(
            lambda p: p.picking_type_id.code == 'outgoing'
        ):
            for move in picking.move_ids.filtered(
                'agrusa_import_purchase_line_id'
            ):
                # Los productos sin seguimiento no requieren lote.
                # La referencia interna manual no es stock.lot.
                if move.product_id.tracking == 'none':
                    continue
    
                allowed = move._agrusa_allowed_import_lots()
    
                for ml in move.move_line_ids.filtered(
                    lambda l: l.quantity > 0
                ):
                    if ml.lot_id not in allowed:
                        raise UserError(_(
                            'AGRUSA: la entrega %s contiene el lote %s '
                            'que no corresponde a la importacion %s. '
                            'Revise la asignacion antes de validar.'
                        ) % (
                            picking.name,
                            ml.lot_id.name or '(sin lote)',
                            move.agrusa_import_purchase_line_id.order_id.name,
                        ))
    
        result = super().button_validate()
    
        # Conservar íntegramente el bloque original que
        # reasigna movimientos tras completar recepciones.
        for picking in self.filtered(
            lambda p: p.picking_type_id.code == 'incoming'
            and p.state == 'done'
        ):
            po_lines = picking.move_ids.mapped('purchase_line_id')
            if not po_lines:
                continue
    
            pending = self.env['stock.move'].search([
                ('agrusa_import_purchase_line_id', 'in', po_lines.ids),
                ('state', 'in', ['confirmed', 'partially_available']),
                ('location_dest_id.usage', '=', 'customer'),
            ])
            if pending:
                pending._action_assign()
    
        return result

