# -*- coding: utf-8 -*-
"""Auditoría complementaria: no modifica la lógica comercial de AGRUSA."""
from markupsafe import Markup, escape
from odoo import api, models, fields

# Campos de negocio, no campos calculados, de infraestructura o de chatter.
ORDER_FIELDS = (
    'partner_id', 'partner_invoice_id', 'partner_shipping_id',
    'client_order_ref', 'origin', 'user_id', 'team_id', 'company_id',
    'pricelist_id', 'payment_term_id', 'fiscal_position_id',
    'date_order', 'validity_date', 'commitment_date', 'expected_date',
    'warehouse_id', 'incoterm', 'incoterm_location', 'note',
    'currency_id', 'total_currency_id', 'total_currency_rate',
    'agrusa_import_fx_rate', 'state',
)
LINE_FIELDS = (
    'product_id', 'name', 'product_uom_qty', 'product_uom_id',
    'price_unit', 'discount', 'tax_id', 'customer_lead',
    'route_id', 'agrusa_import_purchase_line_id',
    'display_type', 'sequence',
)


def _tracked(record, names):
    result = {}
    for name in names:
        field = record._fields.get(name)
        if not field or not field.store or field.related:
            continue
        # Odoo 19 define algunos campos comerciales como calculados y
        # almacenados. La cantidad debe auditarse cuando se escribe
        # explícitamente, aunque tenga compute/inverse.
        if field.compute and name != 'product_uom_qty':
            continue
        val = record[name]
        if field.type == 'many2one':
            result[name] = (val.id or False, val.display_name if val else '—')
        elif field.type == 'many2many':
            result[name] = (tuple(sorted(val.ids)), ', '.join(val.mapped('display_name')) or '—')
        elif field.type in ('date', 'datetime'):
            result[name] = (str(val or ''), str(val or '—'))
        elif field.type == 'selection':
            selections = field._description_selection(record.env)
            label = dict(selections).get(val, val)
            result[name] = (val, str(label or '—'))
        elif field.type == 'boolean':
            result[name] = (bool(val), 'Sí' if val else 'No')
        elif field.type in ('float', 'monetary'):
            result[name] = (float(val or 0), '%.6f' % (val or 0))
        else:
            result[name] = (val or False, str(val) if val not in (False, None, '') else '—')
    return result


def _differences(record, before, names, excluded=()):
    after = _tracked(record, names)
    changes = []
    for name, old in before.items():
        if name in excluded or name not in after or old[0] == after[name][0]:
            continue
        label = record._fields[name].string or name
        changes.append((label, old[1], after[name][1]))
    return changes


def _publish(order, title, changes):
    if not changes or not order.exists():
        return
    rows = Markup('').join(
        Markup('<li><b>%s:</b> %s → %s</li>') %
        (escape(label), escape(str(old)), escape(str(new)))
        for label, old, new in changes
    )
    body = (Markup('<b>%s</b><br/><b>Usuario:</b> %s<br/><ul>%s</ul>') %
            (escape(title), escape(order.env.user.display_name), rows))
    order.message_post(body=body, subtype_xmlid='mail.mt_note')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def write(self, vals):
        if self.env.context.get('_agrusa_skip_audit'):
            return super().write(vals)
        keys = [k for k in vals if k in ORDER_FIELDS and k != 'state']
        # Odoo ya comunica los cambios de estado y campos con tracking nativo.
        keys = [k for k in keys if k in self._fields and not getattr(self._fields[k], 'tracking', False)]
        before = {order.id: _tracked(order, keys) for order in self} if keys else {}
        result = super().write(vals)
        for order in self:
            changes = _differences(order, before.get(order.id, {}), keys)
            _publish(order, 'Auditoría AGRU – cambios en cabecera', changes)
        return result


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if self.env.context.get('_agrusa_skip_audit'):
            return lines
        for line in lines:
            if not line.order_id or not line.order_id.exists():
                continue
            snapshot = _tracked(line, LINE_FIELDS)
            changes = [(line._fields[k].string or k, '—', v[1])
                       for k, v in snapshot.items()
                       if k in ('product_id', 'name', 'product_uom_qty', 'price_unit',
                                'discount', 'agrusa_import_purchase_line_id')]
            _publish(line.order_id, 'Auditoría AGRU – línea agregada (#%s)' % line.id, changes)
        return lines

    def write(self, vals):
        if self.env.context.get('_agrusa_skip_audit'):
            return super().write(vals)
        keys = [k for k in vals if k in LINE_FIELDS and k in self._fields]
        before = {line.id: (_tracked(line, keys), line.order_id, line.product_id.display_name)
                  for line in self} if keys else {}
        result = super().write(vals)
        for line in self:
            old, order, product = before.get(line.id, ({}, False, ''))
            # El módulo de importaciones ya registra con mayor detalle los precios
            # manuales en cotizaciones. Evitamos publicar una segunda nota.
            skip_price = ('price_unit',) if (
                'price_unit' in vals and not self.env.context.get('_agru_skip_currency_sync')
                and order.state in ('draft', 'sent')
            ) else ()
            changes = _differences(line, old, keys, excluded=skip_price)
            _publish(order, 'Auditoría AGRU – línea modificada (#%s, %s)' %
                     (line.id, product), changes)
        return result

    def unlink(self):
        snapshots = []
        if not self.env.context.get('_agrusa_skip_audit'):
            for line in self:
                if line.order_id:
                    snap = _tracked(line, LINE_FIELDS)
                    changes = [(line._fields[k].string or k, v[1], 'Eliminado')
                               for k, v in snap.items()
                               if k in ('product_id', 'name', 'product_uom_qty',
                                        'price_unit', 'agrusa_import_purchase_line_id')]
                    snapshots.append((line.order_id, line.id, changes))
        result = super().unlink()
        for order, line_id, changes in snapshots:
            _publish(order, 'Auditoría AGRU – línea eliminada (#%s)' % line_id, changes)
        return result
