# -*- coding: utf-8 -*-
"""Sincronizacion de fechas comerciales con movimientos de salida pendientes."""
from datetime import datetime, time
import pytz
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _agrusa_sync_stock_move_dates(self):
        """Ajusta exclusivamente fechas de movimientos de salida no finalizados.

        No modifica cantidades, reservas, lineas de operaciones ni fechas
        de recepcion de importaciones.
        """
        for line in self:
            target = fields.Date.to_date(line.agrusa_delivery_date_approx)
            if not target:
                continue
            # El campo comercial es una fecha sin hora. Mediodia local evita
            # que el dia visible cambie por conversiones de zona horaria.
            tz_name = line.order_id.company_id.partner_id.tz or self.env.user.tz or 'America/Santiago'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.timezone('America/Santiago')
            local_dt = tz.localize(datetime.combine(target, time(12, 0)), is_dst=None)
            utc_dt = local_dt.astimezone(pytz.UTC).replace(tzinfo=None)
            dt_value = fields.Datetime.to_string(utc_dt)
            moves = line.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
                and m.picking_type_id.code == 'outgoing'
            )
            for move in moves:
                updates = {}
                if move.date != utc_dt:
                    updates['date'] = dt_value
                if 'date_deadline' in move._fields and move.date_deadline != utc_dt:
                    updates['date_deadline'] = dt_value
                if updates:
                    move.with_context(agrusa_skip_delivery_sync=True).write(updates)
