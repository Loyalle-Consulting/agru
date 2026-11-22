import base64
import io
import json
import math
from datetime import date, datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

COLUMNS = [
    'id_regla', 'aplicacion', 'codigo_producto', 'id_producto', 'id_plantilla',
    'id_categoria', 'cantidad_minima', 'fecha_inicio', 'fecha_fin',
    'calculo', 'precio_fijo', 'porcentaje', 'base', 'id_tarifa_base',
    'descuento_formula', 'redondeo', 'recargo', 'margen_minimo', 'margen_maximo',
]
MAP_APPLIED = {'global':'3_global', 'categoria':'2_product_category', 'producto':'1_product', 'variante':'0_product_variant'}
REVERSE_APPLIED = {v:k for k,v in MAP_APPLIED.items()}
NUMBERS = {'cantidad_minima':'min_quantity', 'precio_fijo':'fixed_price', 'porcentaje':'percent_price', 'descuento_formula':'price_discount', 'redondeo':'price_round', 'recargo':'price_surcharge', 'margen_minimo':'price_min_margin', 'margen_maximo':'price_max_margin'}
MAPPING = {'fecha_inicio':'date_start', 'fecha_fin':'date_end', 'calculo':'compute_price', 'base':'base'}
FIELDS = ['applied_on','product_id','product_tmpl_id','categ_id','min_quantity','date_start','date_end','compute_price','fixed_price','percent_price','base','base_pricelist_id','price_discount','price_round','price_surcharge','price_min_margin','price_max_margin']

def snapshot(item):
    if not item:
        return ''
    result = {}
    for key in FIELDS:
        val = item[key]
        result[key] = val.id if key in ('product_id','product_tmpl_id','categ_id','base_pricelist_id') else (str(val) if isinstance(val, (date, datetime)) else val)
    return json.dumps(result, sort_keys=True, default=str)

def fmt(v):
    return v if v is not None else ''

class AgrusaPriceWizard(models.TransientModel):
    _name = 'agrusa.price.wizard'
    _description = 'Asistente masivo de tarifas AGRUSA'

    pricelist_id = fields.Many2one('product.pricelist', string='Tarifa', required=True)
    upload = fields.Binary(string='Archivo Excel', attachment=False)
    upload_name = fields.Char()
    export_file = fields.Binary(string='Excel generado', readonly=True, attachment=False)
    export_name = fields.Char(readonly=True)
    state = fields.Selection([('draft','Preparar'),('preview','Revisar'),('done','Aplicado')], default='draft', required=True)
    preview_ids = fields.One2many('agrusa.price.preview','wizard_id', string='Vista previa')
    total_rows = fields.Integer(compute='_compute_stats')
    error_rows = fields.Integer(compute='_compute_stats')
    changed_rows = fields.Integer(compute='_compute_stats')
    batch_id = fields.Many2one('agrusa.price.batch', readonly=True)

    @api.depends('preview_ids.status')
    def _compute_stats(self):
        for rec in self:
            rec.total_rows = len(rec.preview_ids)
            rec.error_rows = len(rec.preview_ids.filtered(lambda x:x.status == 'error'))
            rec.changed_rows = len(rec.preview_ids.filtered(lambda x:x.status in ('create','update')))

    def _reload(self):
        return {'type':'ir.actions.act_window','res_model':self._name,'res_id':self.id,'view_mode':'form','target':'current'}

    def action_export(self):
        self.ensure_one()
        wb = Workbook()
        ws = wb.active
        ws.title = 'Tarifa'
        ws.append(COLUMNS)
        for item in self.env['product.pricelist.item'].search([('pricelist_id','=',self.pricelist_id.id)], order='id'):
            ws.append([
                item.id, REVERSE_APPLIED.get(item.applied_on,''), (item.product_id.default_code or '' if item.product_id else (item.product_tmpl_id.default_code or '' if item.product_tmpl_id else '')),
                item.product_id.id or '', item.product_tmpl_id.id or '', item.categ_id.id or '',
                item.min_quantity, str(item.date_start or ''), str(item.date_end or ''), item.compute_price,
                item.fixed_price, item.percent_price, item.base, item.base_pricelist_id.id or '',
                item.price_discount, item.price_round, item.price_surcharge, item.price_min_margin, item.price_max_margin,
            ])
        for cell in ws[1]:
            cell.fill = PatternFill('solid', fgColor='153C60')
            cell.font = Font(color='FFFFFF', bold=True)
            cell.alignment = Alignment(wrap_text=True)
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            letter = col[0].column_letter
            ws.column_dimensions[letter].width = min(25, max(16, len(str(col[0].value))+3))
        guide = wb.create_sheet('Instrucciones')
        for row in [
            ['AGRUSA - Importacion de tarifas'],
            ['Editar hoja Tarifa. No cambiar los encabezados.'],
            ['id_regla: conservar para actualizar; dejar vacio para crear una nueva regla.'],
            ['codigo_producto: referencia interna AGRU; se prioriza sobre id_producto e id_plantilla.'],
            ['aplicacion: global, categoria, producto, variante.'],
            ['Para producto o variante: usar codigo_producto (referencia interna AGRU). Los ID tecnicos son opcionales.'],
            ['Para categoria: id_categoria; para global: sin producto ni categoria.'],
            ['calculo: fixed, percentage, formula.'],
            ['base: list_price, standard_price, pricelist (solo formula).'],
            ['id_tarifa_base: obligatorio si base = pricelist.'],
            ['Fechas: AAAA-MM-DD; dejar en blanco si no aplican.'],
            ['La importacion NO elimina reglas omitidas del archivo.'],
            ['Importar primero, revisar errores y confirmar cambios.'],
            ['No modificar los precios de importacion asociados a ordenes de compra.'],
        ]: guide.append(row)
        guide.column_dimensions['A'].width = 110
        guide['A1'].font = Font(bold=True, size=14, color='153C60')
        out = io.BytesIO()
        wb.save(out)
        self.write({'export_file':base64.b64encode(out.getvalue()), 'export_name':'AGRUSA_Tarifa_%s.xlsx' % self.pricelist_id.id})
        return self._reload()

    def _parse(self, raw):
        data = {}
        for k in COLUMNS:
            val = raw.get(k)
            data[k] = val.strip() if isinstance(val,str) else val
        applied = MAP_APPLIED.get(str(data['aplicacion'] or '').lower())
        if not applied:
            raise ValidationError('aplicacion debe ser global, categoria, producto o variante')
        compute = str(data['calculo'] or 'fixed').lower()
        if compute not in ('fixed','percentage','formula'):
            raise ValidationError('calculo debe ser fixed, percentage o formula')
        vals = {'pricelist_id':self.pricelist_id.id, 'applied_on':applied, 'compute_price':compute}
        for col, field in NUMBERS.items():
            value = data[col]
            if value in (None,''):
                if col == 'precio_fijo' and compute == 'fixed':
                    raise ValidationError('Precio fijo obligatorio para calculo fixed')
                if col == 'porcentaje' and compute == 'percentage':
                    raise ValidationError('Porcentaje obligatorio para calculo percentage')
                value = 0
            try:
                n = float(value)
            except (TypeError,ValueError):
                raise ValidationError('%s debe ser numerico' % col)
            if not math.isfinite(n):
                raise ValidationError('%s no es un numero valido' % col)
            vals[field] = n
        if vals['min_quantity'] < 0 or vals['fixed_price'] < 0 or vals['price_round'] < 0:
            raise ValidationError('Cantidad, precio fijo y redondeo no pueden ser negativos')
        for col, field in (('fecha_inicio','date_start'),('fecha_fin','date_end')):
            value = data[col]
            if isinstance(value, datetime): value = value.date()
            if value not in ('',None):
                try: value = fields.Date.to_date(value)
                except Exception: raise ValidationError('%s debe ser AAAA-MM-DD' % col)
            vals[field] = value or False
        if vals['date_start'] and vals['date_end'] and vals['date_start'] > vals['date_end']:
            raise ValidationError('Fecha de inicio posterior a fecha final')
        vals.update({'product_id':False,'product_tmpl_id':False,'categ_id':False,'base_pricelist_id':False})
        Product = self.env['product.product']
        Template = self.env['product.template']
        code = str(data['codigo_producto'] or '').strip()
        def find_by_reference():
            if not code:
                return Product.browse()
            matches = Product.search([('default_code', '=', code)])
            if not matches:
                raise ValidationError('Referencia interna inexistente: %s' % code)
            return matches
        if applied == '0_product_variant':
            matches = find_by_reference()
            if code:
                if len(matches) != 1:
                    raise ValidationError('Referencia de variante ambigua: %s' % code)
                product = matches
            else:
                pid = data['id_producto']
                if not pid:
                    raise ValidationError('Indique codigo_producto o id_producto para variante')
                product = Product.browse(int(pid)).exists()
            if not product:
                raise ValidationError('Variante inexistente')
            vals['product_id'] = product.id
            vals['product_tmpl_id'] = product.product_tmpl_id.id
        elif applied == '1_product':
            if code:
                matches = find_by_reference()
                templates = matches.mapped('product_tmpl_id')
                if len(templates) != 1:
                    raise ValidationError('Referencia interna ambigua entre plantillas: %s' % code)
                template = templates
            else:
                tid = data['id_plantilla']
                if not tid:
                    raise ValidationError('Indique codigo_producto o id_plantilla para producto')
                template = Template.browse(int(tid)).exists()
            if not template:
                raise ValidationError('Plantilla inexistente')
            vals['product_tmpl_id'] = template.id
        elif applied == '2_product_category':
            cid = data['id_categoria']
            if not cid: raise ValidationError('id_categoria obligatorio')
            cat = self.env['product.category'].browse(int(cid)).exists()
            if not cat: raise ValidationError('Categoria inexistente')
            vals['categ_id'] = cat.id
        base = str(data['base'] or 'list_price').lower()
        if base not in ('list_price','standard_price','pricelist'):
            raise ValidationError('base no valida')
        vals['base'] = base
        if compute == 'formula' and base == 'pricelist':
            if not data['id_tarifa_base']: raise ValidationError('id_tarifa_base obligatorio')
            bp = self.env['product.pricelist'].browse(int(data['id_tarifa_base'])).exists()
            if not bp or bp.id == self.pricelist_id.id: raise ValidationError('Tarifa base inexistente o igual a tarifa destino')
            vals['base_pricelist_id'] = bp.id
        item = False
        if data['id_regla'] not in (None,''):
            try: item_id = int(data['id_regla'])
            except (TypeError,ValueError): raise ValidationError('id_regla invalido')
            item = self.env['product.pricelist.item'].browse(item_id).exists()
            if not item or item.pricelist_id.id != self.pricelist_id.id:
                raise ValidationError('Regla no pertenece a la tarifa seleccionada: %s' % item_id)
        return vals, item

    def action_preview(self):
        self.ensure_one()
        if not self.upload: raise UserError('Seleccione un archivo Excel .xlsx')
        if not (self.upload_name or '').lower().endswith('.xlsx'):
            raise UserError('Solo se admite formato .xlsx')
        raw_bytes = base64.b64decode(self.upload)
        if len(raw_bytes) > 12 * 1024 * 1024: raise UserError('Archivo demasiado grande (maximo 12 MB)')
        try:
            book = load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
            sheet = book['Tarifa'] if 'Tarifa' in book.sheetnames else book.active
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if not header or list(header[:len(COLUMNS)]) != COLUMNS:
                raise UserError('Encabezados incorrectos. Descargue la plantilla desde Exportar Excel.')
        except UserError: raise
        except Exception as exc: raise UserError('No se pudo abrir Excel: %s' % str(exc))
        self.preview_ids.unlink()
        seen = set()
        count = 0
        for number, cells in enumerate(rows, 2):
            if not any(v is not None and v != '' for v in cells): continue
            count += 1
            if count > 5000: raise UserError('Maximo 5000 filas por operacion')
            raw = dict(zip(COLUMNS, cells))
            try:
                vals, item = self._parse(raw)
                key = item.id if item else None
                if key and key in seen: raise ValidationError('Regla duplicada en archivo')
                if key: seen.add(key)
                before = snapshot(item)
                status = 'create' if not item else 'update'
                if item and all((item[k].id if k in ('product_id','product_tmpl_id','categ_id','base_pricelist_id') else (str(item[k]) if k in ('date_start','date_end') and item[k] else item[k])) == (str(v) if k in ('date_start','date_end') and v else (v or False)) for k,v in vals.items() if k != 'pricelist_id'):
                    status = 'skip'
                title = item.display_name if item else '%s / %s' % (raw.get('aplicacion') or '',raw.get('codigo_producto') or raw.get('id_plantilla') or raw.get('id_categoria') or 'Global')
                self.env['agrusa.price.preview'].create({'wizard_id':self.id,'row_number':number,'description':title,'status':status,'item_id':item.id if item else False,'before':before,'after':json.dumps(vals,default=str,sort_keys=True)})
            except Exception as exc:
                self.env['agrusa.price.preview'].create({'wizard_id':self.id,'row_number':number,'description':str(raw.get('codigo_producto') or raw.get('id_regla') or ''),'status':'error','error_message':str(exc)})
        book.close()
        if not count: raise UserError('El archivo no contiene filas de datos')
        self.state = 'preview'
        return self._reload()

    def action_apply(self):
        self.ensure_one()
        if self.state != 'preview': raise UserError('Debe generar vista previa antes de aplicar')
        if self.error_rows: raise UserError('Corrija todas las filas con errores antes de aplicar')
        if not self.changed_rows: raise UserError('No hay modificaciones pendientes')
        Item = self.env['product.pricelist.item']
        # Verificacion previa completa: no escribir parcialmente si hubo cambios concurrentes.
        for line in self.preview_ids.filtered(lambda x:x.status == 'update'):
            if not line.item_id.exists() or snapshot(line.item_id) != line.before:
                raise UserError('La regla de fila %s cambio desde la vista previa. Vuelva a importar.' % line.row_number)
        batch = self.env['agrusa.price.batch'].create({'name':'Actualizacion tarifa %s - %s' % (self.pricelist_id.display_name,fields.Datetime.now()),'pricelist_id':self.pricelist_id.id})
        for line in self.preview_ids.filtered(lambda x:x.status in ('create','update')).sorted('row_number'):
            vals = json.loads(line.after)
            item = line.item_id if line.status == 'update' else Item
            if line.status == 'update': item.write(vals)
            else: item = Item.create(vals)
            self.env['agrusa.price.batch.line'].create({'batch_id':batch.id,'item_id':item.id,'action':line.status,'description':line.description,'before':line.before or '', 'after':snapshot(item)})
        batch.message_post(body=_('Actualizacion masiva aplicada: %s reglas modificadas por %s.') % (self.changed_rows,self.env.user.display_name))
        self.write({'state':'done','batch_id':batch.id})
        return {'type':'ir.actions.act_window','res_model':'agrusa.price.batch','res_id':batch.id,'view_mode':'form','target':'current'}

class AgrusaPricePreview(models.TransientModel):
    _name = 'agrusa.price.preview'
    _description = 'Vista previa de cambios de tarifas AGRUSA'
    _order = 'row_number'

    wizard_id = fields.Many2one('agrusa.price.wizard', required=True, ondelete='cascade')
    row_number = fields.Integer(string='Fila', readonly=True)
    description = fields.Char(string='Regla', readonly=True)
    status = fields.Selection([('create','Crear'),('update','Actualizar'),('skip','Sin cambios'),('error','Error')], readonly=True)
    error_message = fields.Char(string='Observacion', readonly=True)
    item_id = fields.Many2one('product.pricelist.item', readonly=True)
    before = fields.Text(readonly=True)
    after = fields.Text(readonly=True)
