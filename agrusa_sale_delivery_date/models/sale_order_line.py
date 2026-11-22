# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    agrusa_delivery_date_manual = fields.Boolean(
        string='Fecha entrega manual', default=False, copy=False)
    agrusa_delivery_date_approx = fields.Date(
        string='Fecha entrega APROX', copy=False,
        help='Fecha comercial editable. En tránsito no puede ser anterior a ETA de la OC más el plazo adicional.')

    def _agrusa_base_date(self):
        self.ensure_one()
        if not self.order_id.date_order:
            return fields.Date.context_today(self)
        dt = fields.Datetime.to_datetime(self.order_id.date_order)
        return fields.Datetime.context_timestamp(self.order_id, dt).date()

    def _agrusa_transit_extra_days(self):
        self.ensure_one()
        value = self.env['ir.config_parameter'].sudo().get_param(
            'agrusa_sale_delivery_date.transit_extra_days', '10')
        try:
            days = int(value)
        except (ValueError, TypeError):
            days = 10
        return max(0, days)

    def _agrusa_transit_min_date(self):
        self.ensure_one()
        po_line = self.agrusa_import_purchase_line_id
        if not po_line or not po_line.date_planned:
            return False
        return fields.Datetime.to_datetime(po_line.date_planned).date() + timedelta(
            days=self._agrusa_transit_extra_days())

    def _agrusa_expected_delivery_date(self):
        self.ensure_one()
        if self.display_type:
            return False
        if self.agrusa_import_purchase_line_id:
            return self._agrusa_transit_min_date()
        return self._agrusa_base_date() + timedelta(days=round(self.customer_lead or 0))

    def _agrusa_days_to(self, date):
        self.ensure_one()
        return (fields.Date.to_date(date) - self._agrusa_base_date()).days

    def _agrusa_validate_min_delivery_date(self):
        for line in self:
            if line.display_type or not line.agrusa_import_purchase_line_id:
                continue
            minimum = line._agrusa_transit_min_date()
            date = fields.Date.to_date(line.agrusa_delivery_date_approx)
            if minimum and date and date < minimum:
                raise ValidationError(_(
                    'La fecha de entrega de %(product)s (%(date)s) es anterior al mínimo '
                    'permitido (%(minimum)s) para la OC %(po)s. '
                    'La fecha mínima corresponde a la ETA más %(days)s días.'
                ) % {
                    'product': line.product_id.display_name,
                    'date': fields.Date.to_string(date),
                    'minimum': fields.Date.to_string(minimum),
                    'po': line.agrusa_import_purchase_line_id.order_id.name,
                    'days': line._agrusa_transit_extra_days(),
                })

    @api.onchange('agrusa_import_purchase_line_id')
    def _onchange_agrusa_import_delivery(self):
        for line in self:
            if line.display_type or line.agrusa_delivery_date_manual:
                continue
            target = line._agrusa_expected_delivery_date()
            if target:
                line.agrusa_delivery_date_approx = target
                line.customer_lead = line._agrusa_days_to(target)

    @api.onchange('customer_lead')
    def _onchange_agrusa_lead(self):
        for line in self:
            if line.display_type:
                continue
            target = line._agrusa_base_date() + timedelta(days=round(line.customer_lead or 0))
            # If both values already match, the lead was synchronized by an
            # automatic onchange; it is not evidence of a manual edit.
            if line.agrusa_delivery_date_approx == target:
                continue
            minimum = line._agrusa_transit_min_date()
            if minimum and target < minimum:
                line.agrusa_delivery_date_approx = minimum
                line.customer_lead = line._agrusa_days_to(minimum)
                return {'warning': {
                    'title': _('Fecha mínima de Tránsito'),
                    'message': _('La fecha mínima para la OC %(po)s es %(date)s.') % {
                        'po': line.agrusa_import_purchase_line_id.order_id.name,
                        'date': fields.Date.to_string(minimum),
                    },
                }}
            line.agrusa_delivery_date_manual = True
            line.agrusa_delivery_date_approx = target

    @api.onchange('agrusa_delivery_date_approx')
    def _onchange_agrusa_date(self):
        for line in self:
            if line.display_type or not line.agrusa_delivery_date_approx:
                continue
            minimum = line._agrusa_transit_min_date()
            if minimum and line.agrusa_delivery_date_approx < minimum:
                line.agrusa_delivery_date_approx = minimum
                line.customer_lead = line._agrusa_days_to(minimum)
                return {'warning': {
                    'title': _('Fecha mínima de Tránsito'),
                    'message': _('La fecha mínima para la OC %(po)s es %(date)s.') % {
                        'po': line.agrusa_import_purchase_line_id.order_id.name,
                        'date': fields.Date.to_string(minimum),
                    },
                }}
            target_lead = line._agrusa_days_to(line.agrusa_delivery_date_approx)
            # Automatic OC onchange sets both fields; do not turn it manual.
            if not line.agrusa_delivery_date_manual and line.agrusa_delivery_date_approx == line._agrusa_expected_delivery_date():
                line.customer_lead = target_lead
                continue
            if line.customer_lead != target_lead:
                line.agrusa_delivery_date_manual = True
                line.customer_lead = target_lead

    def _agrusa_delivery_updates(self, vals, creating=False, previous=None):
        self.ensure_one()
        if self.display_type:
            return {}
        previous = previous or {}
        reset = vals.get('agrusa_delivery_date_manual', None) is False and 'agrusa_delivery_date_manual' in vals
        po_changed = 'agrusa_import_purchase_line_id' in vals or 'agrusa_supply_origin' in vals
        date_supplied = bool(vals.get('agrusa_delivery_date_approx'))
        lead_supplied = 'customer_lead' in vals
        target = self._agrusa_expected_delivery_date()
        date_changed = date_supplied and (creating or previous.get('date') != self.agrusa_delivery_date_approx)
        lead_changed = lead_supplied and (creating or previous.get('lead') != self.customer_lead)
        manual = self.agrusa_delivery_date_manual

        if reset:
            manual = False
        elif po_changed and not manual:
            # Selecting/changing an OC is automatic even if the web client
            # also submitted old date/lead values.
            manual = False
        elif creating:
            # Odoo may send date and lead populated by automatic onchanges.
            # Only a date different from the calculated minimum signals an
            # explicit override on a new transit line.
            if self.agrusa_import_purchase_line_id:
                manual = bool(date_supplied and target and self.agrusa_delivery_date_approx != target)
            else:
                manual = bool(vals.get('agrusa_delivery_date_manual', False))
        elif date_changed or lead_changed:
            # Date takes precedence when both values are supplied. Avoid
            # flagging an automatic pair that already matches the target.
            if date_changed and self.agrusa_import_purchase_line_id and self.agrusa_delivery_date_approx == target:
                manual = False if not previous.get('manual') else manual
            else:
                manual = True

        changes = {}
        if not manual and target and (reset or po_changed or creating):
            changes['agrusa_delivery_date_approx'] = target
            changes['customer_lead'] = self._agrusa_days_to(target)
        elif date_changed and not (po_changed and not manual):
            changes['customer_lead'] = self._agrusa_days_to(self.agrusa_delivery_date_approx)
        elif lead_changed and not (po_changed and not manual):
            changes['agrusa_delivery_date_approx'] = self._agrusa_base_date() + timedelta(
                days=round(self.customer_lead or 0))
        elif not manual and target:
            changes['agrusa_delivery_date_approx'] = target
            changes['customer_lead'] = self._agrusa_days_to(target)

        if self.agrusa_delivery_date_manual != manual:
            changes['agrusa_delivery_date_manual'] = manual
        return {key: value for key, value in changes.items() if self[key] != value}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for line, vals in zip(records, vals_list):
            if line.display_type:
                continue
            changes = line._agrusa_delivery_updates(vals, creating=True)
            if changes:
                super(SaleOrderLine, line.with_context(agrusa_skip_delivery_sync=True)).write(changes)
        records._agrusa_validate_min_delivery_date()
        records._agrusa_sync_stock_move_dates()
        return records

    def write(self, vals):
        if self.env.context.get('agrusa_skip_delivery_sync'):
            return super().write(vals)
        watched = {
            'customer_lead', 'order_id', 'agrusa_import_purchase_line_id',
            'agrusa_supply_origin', 'agrusa_delivery_date_approx',
            'agrusa_delivery_date_manual',
        }
        previous = {
            line.id: {
                'date': line.agrusa_delivery_date_approx,
                'lead': line.customer_lead,
                'manual': line.agrusa_delivery_date_manual,
            } for line in self
        } if watched.intersection(vals) else {}
        result = super().write(vals)
        if previous:
            for line in self:
                updates = line._agrusa_delivery_updates(vals, previous=previous[line.id])
                if updates:
                    super(SaleOrderLine, line.with_context(agrusa_skip_delivery_sync=True)).write(updates)
            # Explicit user changes must respect the minimum. A later ETA
            # change is handled separately in purchase_order.py and can leave
            # a manual date pending review until confirmation.
            self._agrusa_validate_min_delivery_date()
            self._agrusa_sync_stock_move_dates()
        return result

    def action_agrusa_reset_delivery_date(self):
        self.write({'agrusa_delivery_date_manual': False})
        return True
