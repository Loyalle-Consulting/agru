# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    total_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda de cotización',
        tracking=True,
        help='Moneda en la que se totaliza el documento. Mientras esté en '
             'Presupuesto o Cotización enviada se puede cambiar y la tasa '
             'se puede editar a mano; las líneas se recalculan '
             'automáticamente. Al confirmar el pedido, moneda y tasa '
             'quedan selladas. Si el pedido vuelve a cotización, se '
             'vuelve a poder editar.',
    )

    # Se mantiene como marca histórica/de auditoría (para el mensaje en el
    # chatter al confirmar), pero YA NO se usa para decidir si se puede
    # editar: eso se decide en vivo mirando el campo "state" del pedido
    # (ver _is_currency_editable), que Odoo mantiene siempre correcto sin
    # importar qué botón se use para pasar de un estado a otro.
    total_currency_locked = fields.Boolean(
        string='Moneda y tasa se sellaron alguna vez',
        readonly=True,
        copy=False,
    )

    original_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda original (lista de precios)',
        readonly=True,
        copy=False,
    )

    total_currency_rate = fields.Float(
        string='Tasa de cambio',
        digits=(24, 12),
        readonly=False,
        copy=False,
        tracking=True,
    )

    total_currency_rate_date = fields.Date(
        string='Fecha de la tasa sugerida',
        readonly=True,
        copy=False,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        store=True,
        readonly=False,
        tracking=True,
    )

    def _is_currency_editable(self):
        """Única fuente de verdad para saber si moneda/tasa se pueden
        tocar: solo mientras el pedido está en Presupuesto o Cotización
        enviada. Se basa en 'state', que Odoo mantiene siempre correcto
        sin importar qué acción se use para cambiar de estado (confirmar,
        cancelar, volver a cotización, etc.) — así nunca queda
        desincronizado con una bandera propia que haya que resetear."""
        self.ensure_one()
        return self.state in ('draft', 'sent')

    def _get_suggested_rate(self, source_currency, target_currency, post_message=True):
        self.ensure_one()
        date_ref = self.date_order and self.date_order.date() or fields.Date.context_today(self)
        company = self.company_id or self.env.company

        rate = source_currency._get_conversion_rate(
            source_currency, target_currency, company, date_ref
        )

        Rate = self.env['res.currency.rate']
        exact = Rate.search([
            ('currency_id', '=', target_currency.id),
            ('name', '=', date_ref),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ], limit=1)
        used_date = date_ref
        if not exact:
            last_rate = Rate.search([
                ('currency_id', '=', target_currency.id),
                ('name', '<=', date_ref),
                '|', ('company_id', '=', company.id), ('company_id', '=', False),
            ], order='name desc', limit=1)
            used_date = last_rate.name if last_rate else date_ref
            if post_message and isinstance(self.id, int) and self.id:
                self.message_post(body=_(
                    "No se encontró tasa de cambio de %(cur)s para el %(date)s. "
                    "Se sugirió la última tasa disponible, del %(used)s."
                ) % {
                    'cur': target_currency.name,
                    'date': date_ref,
                    'used': used_date,
                })

        return rate, used_date

    def _apply_total_currency_to_lines(self):
        """Recalcula el price_unit de cada línea desde su precio original
        (nunca desde el valor ya convertido), usando la tasa ACTUAL. Es
        idempotente: se puede llamar todas las veces que haga falta sin
        acumular error."""
        self.ensure_one()
        if not self.total_currency_rate:
            return
        for line in self.order_line:
            if line.display_type:
                continue
            new_price = line._get_converted_price(self.total_currency_rate)
            if not line.agru_manual_price and abs(new_price - line.price_unit) > 0.001:
                line.price_unit = new_price

    def _sync_rate_for_currency(self, post_message=False):
        """Sugiere una tasa nueva (según la lista oficial de tasas de
        cambio) para la moneda de cotización actual, y aplica de una a
        las líneas."""
        self.ensure_one()
        source = self.pricelist_id.currency_id or self.company_id.currency_id
        target = self.total_currency_id or source
        self.original_currency_id = source
        self.currency_id = target
        if target == source:
            self.total_currency_rate = 1.0
            self.total_currency_rate_date = fields.Date.context_today(self)
        else:
            rate, used_date = self._get_suggested_rate(source, target, post_message=post_message)
            self.total_currency_rate = rate
            self.total_currency_rate_date = used_date
        self._apply_total_currency_to_lines()

    @api.onchange('pricelist_id')
    def _onchange_pricelist_id_loyalle(self):
        for order in self:
            if not order._is_currency_editable():
                continue
            # La lista de precios cambió. El precio de referencia de cada
            # línea pertenece a la lista ANTERIOR, por lo que debe
            # recalcularse contra la nueva lista. Esto NO significa
            # convertir el último precio visible: _get_reliable_pricelist_price
            # vuelve siempre al precio/regla de origen.
            for line in order.order_line:
                if not line.display_type and line.price_unit_original:
                    line.price_unit_original = 0.0

            # AGRU: al seleccionar una tarifa en otra moneda se entiende que
            # la cotización pasa a ESA moneda. Antes total_currency_id quedaba
            # pegada a la moneda anterior (ej. Tarifa EUR + cotización CLP),
            # y el módulo aplicaba una segunda conversión EUR -> CLP, generando
            # importes enormes. Alinear ambos campos elimina esa conversión
            # cruzada accidental. El usuario aún puede cambiar después
            # "Moneda de cotización" manualmente si necesita cotizar una
            # tarifa en una moneda distinta.
            new_currency = order.pricelist_id.currency_id or order.company_id.currency_id
            order.total_currency_id = new_currency
            order.currency_id = new_currency
            order._sync_rate_for_currency(post_message=False)

    @api.onchange('total_currency_id')
    def _onchange_total_currency_id_loyalle(self):
        for order in self:
            if not order._is_currency_editable():
                continue
            order._sync_rate_for_currency(post_message=False)

    @api.onchange('total_currency_rate')
    def _onchange_total_currency_rate_loyalle(self):
        # El usuario editó la tasa a mano: se aplica de inmediato a las
        # líneas, sin necesidad de ningún botón.
        for order in self:
            if not order._is_currency_editable():
                continue
            order._apply_total_currency_to_lines()

    @api.onchange('date_order')
    def _onchange_date_order_loyalle(self):
        # Si cambia la fecha de cotización, la tasa sugerida debe
        # corresponder a esa fecha (no siempre a "hoy").
        for order in self:
            if not order._is_currency_editable():
                continue
            source = order.pricelist_id.currency_id or order.company_id.currency_id
            if order.total_currency_id and order.total_currency_id != source:
                order._sync_rate_for_currency(post_message=False)

    def action_confirm(self):
        for order in self:
            if order._is_currency_editable():
                order._apply_total_currency_to_lines()
        res = super().action_confirm()
        for order in self:
            if order.total_currency_id and not order.total_currency_locked:
                order.total_currency_locked = True
                if order.total_currency_rate and order.original_currency_id \
                        and order.original_currency_id != order.total_currency_id:
                    order.message_post(body=_(
                        "Moneda y tasa de cambio selladas al confirmar el pedido: "
                        "1 %(from)s = %(rate)s %(to)s."
                    ) % {
                        'from': order.original_currency_id.name,
                        'rate': '%.12f' % order.total_currency_rate,
                        'to': order.total_currency_id.name,
                    })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if not order._is_currency_editable():
                continue
            if not order.total_currency_id:
                order.total_currency_id = order.pricelist_id.currency_id or order.company_id.currency_id
            if not order.currency_id:
                order.currency_id = order.total_currency_id
            if not order.total_currency_rate:
                source = order.pricelist_id.currency_id or order.company_id.currency_id
                target = order.total_currency_id or source
                if target == source:
                    order.total_currency_rate = 1.0
                else:
                    rate, used_date = order._get_suggested_rate(source, target, post_message=True)
                    order.total_currency_rate = rate
                    order.total_currency_rate_date = used_date
            # Pasada de corrección final: garantiza que lo grabado en BD
            # sea consistente con la tasa persistida, sin importar qué
            # haya pasado en el navegador durante la edición en vivo.
            order._apply_total_currency_to_lines()
        return orders


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Precio de referencia en la moneda ORIGINAL de la lista de precios.
    # Se captura una sola vez y nunca se vuelve a tocar.
    price_unit_original = fields.Float(
        digits=(24, 12),
        copy=False,
    )

    def _get_pricelist_fallback_base(self):
        """Datos crudos del precio base de la ficha (sin ninguna
        conversión): el precio, la moneda declarada como base de ese
        precio, y si el producto tiene o no una regla PROPIA en la lista
        de precios del pedido (si la tiene, ese precio de fallback no
        debería usarse — manda la regla)."""
        self.ensure_one()
        order = self.order_id
        product = self.product_id
        company = order.company_id or order.env.company
        base_price = product.list_price
        base_currency = product.product_tmpl_id.list_price_currency_id or company.currency_id
        has_own_rule = bool(self.env['product.pricelist.item'].search_count([
            ('pricelist_id', '=', order.pricelist_id.id),
            '|',
                ('product_id', '=', product.id),
                '&', ('product_tmpl_id', '=', product.product_tmpl_id.id),
                     ('product_id', '=', False),
        ]))
        return base_price, base_currency, has_own_rule

    def _get_converted_price(self, rate):
        """Precio final de la línea en la moneda de cotización.

        Caso general: se parte del precio 'original' ya expresado en la
        moneda de la LISTA DE PRECIOS (price_unit_original, calculado
        una sola vez por _get_reliable_pricelist_price) y se multiplica
        por la tasa (lista -> cotización).

        Caso especial, A PROPÓSITO SIN NINGÚN CÁLCULO: el producto no
        tiene regla propia en la lista (se está usando el precio de la
        ficha como fallback) Y la moneda declarada como base de esa
        ficha coincide EXACTAMENTE con la moneda final de la cotización.
        Sin este atajo el precio pasaría dos veces por conversión de
        moneda (base -> moneda de la lista -> moneda de cotización) y,
        aunque cada conversión individual use la tasa sin redondear, el
        valor intermedio queda guardado en price_unit_original con la
        precisión de ese campo — eso deja una diferencia de uno o dos
        pesos que no debería existir, ya que en este caso puntual la
        moneda de origen y la de destino son la misma. Se traspasa el
        precio de la ficha tal cual."""
        self.ensure_one()
        order = self.order_id
        base_price, base_currency, has_own_rule = self._get_pricelist_fallback_base()
        if not has_own_rule and base_price and base_currency == order.total_currency_id:
            return base_price
        if not self.price_unit_original:
            self.price_unit_original = self._get_reliable_pricelist_price()
        return self.price_unit_original * rate

    def _get_reliable_pricelist_price(self):
        """Calcula el precio 'de verdad' según la lista de precios.

        Se calculan DOS candidatos y se elige el confiable:

        1. El nativo de Odoo (pricelist._get_product_price), que en teoría
           debería ser siempre correcto — pero se comprobó que, para
           algunos productos, devuelve el precio base de la ficha SIN
           convertir a la moneda de la lista, incluso cuando declaramos
           monedas distintas (un bug/inconsistencia del propio motor de
           precios de Odoo en este tipo de caso).
        2. El propio: toma el precio base de la ficha y lo convierte
           manualmente desde su 'Moneda del precio base' hacia la moneda
           de la lista, usando la tasa del día.

        Si el resultado nativo es sospechosamente IGUAL al precio base
        sin convertir —a pesar de que las monedas declaradas son
        distintas, o sea, DEBERÍA haberse convertido— se descarta y se
        usa el cálculo propio en su lugar."""
        self.ensure_one()
        order = self.order_id
        pricelist = order.pricelist_id
        product = self.product_id
        if not pricelist or not product:
            return self.price_unit

        company = order.company_id or order.env.company
        qty = self.product_uom_qty or 1.0
        base_price, base_currency, has_own_rule = self._get_pricelist_fallback_base()
        pricelist_currency = pricelist.currency_id
        date_ref = order.date_order and order.date_order.date() or fields.Date.context_today(order)

        manual_price = base_price
        if base_price and base_currency != pricelist_currency:
            # Se usa la tasa CRUDA (sin redondear) en vez de _convert(),
            # que internamente redondea a la precisión de la moneda de
            # destino (ej. 2 decimales en USD). Para productos cuyo
            # precio base está en pesos pero la lista está en dólares,
            # ese redondeo intermedio perdía precisión (250 CLP -> 0,27
            # USD redondeado -> 248,97 CLP al reconvertir, en vez de 250)
            # — al no redondear acá, esa pérdida desaparece. Aun así, el
            # valor final queda guardado en price_unit_original con la
            # precisión de ese campo, así que un caso puntual (fallback +
            # moneda base == moneda final de la cotización) se resuelve
            # aparte en _get_converted_price, sin pasar por acá.
            rate = base_currency._get_conversion_rate(
                base_currency, pricelist_currency, company, date_ref
            )
            manual_price = base_price * rate

        native_price = None
        if has_own_rule:
            try:
                native_price = pricelist._get_product_price(product, qty, order.partner_id)
            except TypeError:
                try:
                    native_price = pricelist._get_product_price(product, qty)
                except Exception:
                    native_price = None
            except Exception:
                native_price = None

        if native_price:
            currencies_differ = base_currency != pricelist_currency
            looks_unconverted = base_price and abs(native_price - base_price) < 0.01
            if currencies_differ and looks_unconverted:
                # Odoo dijo que había una regla aplicable, pero el número
                # que entregó es el precio base sin ninguna conversión —
                # no es confiable: se usa el cálculo propio.
                return manual_price
            return native_price

        return manual_price or self.price_unit

    @api.onchange('product_id', 'product_uom_qty')
    def _onchange_apply_total_currency(self):
        for line in self:
            order = line.order_id
            if line.display_type or not order._is_currency_editable():
                continue
            if not order.total_currency_rate:
                continue
            new_price = line._get_converted_price(order.total_currency_rate)
            if not line.agru_manual_price and abs(new_price - line.price_unit) > 0.001:
                line.price_unit = new_price

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            order = line.order_id
            if line.display_type or not order._is_currency_editable():
                continue
            if not order.total_currency_rate:
                continue
            correct_price = line._get_converted_price(order.total_currency_rate)
            if not line.agru_manual_price and abs(correct_price - line.price_unit) > 0.001:
                line.with_context(_agru_skip_currency_sync=True).price_unit = correct_price
        return lines

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('_agru_skip_currency_sync'):
            return res
        if 'product_id' in vals and 'price_unit' not in vals:
            # Algunas integraciones (ej. sitio web, importaciones) actualizan
            # el carrito con llamadas directas al modelo, sin pasar por un
            # formulario — ahí ningún onchange se dispara. Esta es la red
            # que cubre ese caso también dentro del backoffice.
            for line in self:
                order = line.order_id
                if line.display_type or not order._is_currency_editable():
                    continue
                if not order.total_currency_rate:
                    continue
                if 'product_id' in vals:
                    # Cambió el producto de la línea (ej. otra variante):
                    # el precio original anterior ya no sirve, se recaptura.
                    line.with_context(_agru_skip_currency_sync=True).write({
                        'price_unit_original': 0.0,
                    })
                correct_price = line._get_converted_price(order.total_currency_rate)
                if not line.agru_manual_price and abs(correct_price - line.price_unit) > 0.001:
                    line.with_context(_agru_skip_currency_sync=True).write({
                        'price_unit': correct_price,
                    })
        return res
