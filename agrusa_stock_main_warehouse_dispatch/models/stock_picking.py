# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    agrusa_main_dispatch_transfer_id = fields.Many2one(
        'stock.picking', string='Traslado previo a Bodega Principal',
        copy=False, readonly=True, index=True,
    )
    agrusa_main_dispatch_origin_id = fields.Many2one(
        'stock.picking', string='Entrega de origen AGRUSA',
        copy=False, readonly=True, index=True,
    )

    def _agrusa_main_warehouse(self):
        self.ensure_one()
        wh = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=', 'WH'),
        ])
        if len(wh) != 1:
            raise UserError(_('AGRUSA: debe existir una unica Bodega Principal con codigo WH.'))
        return wh

    def _agrusa_dispatch_required(self):
        self.ensure_one()
        if self.picking_type_code != 'outgoing' or self.state in ('done', 'cancel'):
            return False
        if not self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')
                                      and m.location_dest_id.usage == 'customer'):
            return False
        wh = self._agrusa_main_warehouse()
        return any(
            m.location_id.id != wh.lot_stock_id.id
            and m.location_id not in self.env['stock.location'].search([
                ('id', 'child_of', wh.lot_stock_id.id)
            ])
            for m in self.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
                and m.location_dest_id.usage == 'customer'
            )
        )

    def _agrusa_open_transfer(self, transfer):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Validar traslado a Bodega Principal'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': transfer.id,
            'target': 'current',
        }

    def _agrusa_prepare_dispatch_transfer(self):
        self.ensure_one()
        existing = self.agrusa_main_dispatch_transfer_id
        if existing:
            if existing.state == 'cancel':
                raise UserError(_('AGRUSA: el traslado vinculado fue cancelado. Revise la entrega.'))
            return self._agrusa_open_transfer(existing) if existing.state != 'done' else False

        if self.backorder_id:
            raise UserError(_('AGRUSA: revise manualmente este backorder antes de convertir su despacho.'))
        moves = self.move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.location_dest_id.usage == 'customer'
        )
        if not moves or any(m.state != 'assigned' for m in moves):
            raise UserError(_('AGRUSA: todas las lineas deben estar completamente disponibles antes del traslado.'))
        if any(not m.move_line_ids or not m.sale_line_id for m in moves):
            raise UserError(_('AGRUSA: entrega sin lineas reservadas o sin venta asociada. Revise antes de continuar.'))
        if any(m.move_dest_ids.filtered(lambda d: d.state == 'done') for m in moves):
            raise UserError(_('AGRUSA: existen devoluciones o movimientos posteriores realizados. '
                              'No se convertira automaticamente esta entrega historica.'))
        if any(m.move_orig_ids.filtered(lambda o: o.state not in ('done', 'cancel')) for m in moves):
            raise UserError(_('AGRUSA: hay operaciones de abastecimiento pendientes.'))

        wh = self._agrusa_main_warehouse()
        source_locations = moves.mapped('move_line_ids.location_id')
        if len(source_locations) != 1:
            raise UserError(_('AGRUSA: la entrega usa multiples ubicaciones fisicas de origen. '
                              'Divida o revise la operacion antes de continuar.'))
        source = source_locations[0]
        if source.usage != 'internal':
            raise UserError(_('AGRUSA: el origen de la transferencia debe ser una ubicacion interna.'))
        if source.id in self.env['stock.location'].search([
            ('id', 'child_of', wh.lot_stock_id.id)
        ]).ids:
            raise UserError(_('AGRUSA: la mercaderia ya esta en Bodega Principal; '
                              'revise la ubicacion de salida.'))

        operation = self.env['stock.picking.type'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=', 'internal'),
            ('warehouse_id', '=', wh.id),
        ], limit=1)
        if not operation:
            raise UserError(_('AGRUSA: falta el tipo de traslado interno de Bodega Principal.'))

        # Important: do not automatically validate a physical transfer.
        # Existing reservations are released only after all safety checks pass.
        reserved = []
        for m in moves:
            for line in m.move_line_ids.filtered(lambda l: l.quantity > 0):
                reserved.append({
                    'move': m,
                    'product': m.product_id,
                    'qty': line.quantity,
                    'location': line.location_id,
                    'lot': line.lot_id,
                    'package': line.package_id,
                    'owner': line.owner_id,
                    'source_position': line.agrusa_source_position_id,
                })
        if not reserved:
            raise UserError(_('AGRUSA: no existen cantidades reservadas para trasladar.'))

        # A fully assigned move can still be partially reserved in edge cases.
        for m in moves:
            qty = sum(r['qty'] for r in reserved if r['move'] == m)
            if abs(qty - m.product_uom_qty) > m.product_id.uom_id.rounding / 2:
                raise UserError(_('AGRUSA: cantidades reservadas distintas de las demandadas. '
                                  'No se permite la conversion automatica.'))

        moves._do_unreserve()
        transfer = self.env['stock.picking'].create({
            'picking_type_id': operation.id,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'origin': '%s / %s' % (self.origin or '', self.name),
            'location_id': source.id,
            'location_dest_id': wh.lot_stock_id.id,
            'agrusa_main_dispatch_origin_id': self.id,
        })
        transfer_moves = self.env['stock.move']
        for m in moves:
            transfer_move = self.env['stock.move'].create({
                'picking_id': transfer.id,
                'company_id': self.company_id.id,
                'product_id': m.product_id.id,
                'product_uom': m.product_uom.id,
                'product_uom_qty': m.product_uom_qty,
                'location_id': source.id,
                'location_dest_id': wh.lot_stock_id.id,
                'move_orig_ids': [(4, origin.id) for origin in m.move_orig_ids],
            })
            transfer_moves |= transfer_move
            # Connect the final delivery to the internal transfer. This is
            # necessary for the custom WH4 requisition reservation restriction.
            m.write({
                'move_orig_ids': [(4, transfer_move.id)],
                'location_id': wh.lot_stock_id.id,
            })
        transfer.action_confirm()
        transfer_moves._action_assign()
        if any(m.state != 'assigned' for m in transfer_moves):
            raise UserError(_('AGRUSA: no se pudo reservar la mercaderia para el traslado interno.'))
        # Do not auto-validate transfer: the warehouse operator must
        # choose the real destination rack position and confirm quantities.
        self.agrusa_main_dispatch_transfer_id = transfer.id
        self.message_post(body=_('AGRUSA: traslado interno %s creado. '
                                 'Valide fisicamente su recepcion en Bodega Principal '
                                 'antes de completar esta entrega.') % transfer.name)
        return self._agrusa_open_transfer(transfer)

    def button_validate(self):
        for picking in self:
            transfer = picking.agrusa_main_dispatch_transfer_id
            if transfer and picking.state not in ('done', 'cancel'):
                if transfer.state != 'done':
                    raise UserError(_('AGRUSA: valide primero el traslado interno %s.') % transfer.name)
                if picking._agrusa_dispatch_required():
                    raise UserError(_('AGRUSA: la entrega sigue apuntando a una bodega secundaria.'))
                pending = picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
                if any(m.state != 'assigned' for m in pending):
                    pending._action_assign()
                if any(m.state != 'assigned' for m in pending):
                    raise UserError(_('AGRUSA: no se pudo reservar la mercaderia recibida '
                                      'en Bodega Principal. Revise posiciones y lotes.'))
            elif picking._agrusa_dispatch_required():
                if len(self) != 1:
                    raise UserError(_('AGRUSA: valide las entregas de bodegas secundarias individualmente.'))
                return picking._agrusa_prepare_dispatch_transfer()
        return super().button_validate()
