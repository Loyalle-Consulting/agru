import requests
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from decimal import Decimal
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

SERIES = {'EUR': 'F072.CLP.EUR.N.O.D', 'USD': 'F073.TCO.PRE.Z.D'}
URL = 'https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx'
TZ = ZoneInfo('America/Santiago')

class Sync(models.Model):
    _name = 'agrusa.currency.sync'
    _description = 'Configuración BCCh'
    _rec_name = 'company_id'
    company_id = fields.Many2one('res.company', required=True, default=lambda s:s.env.company)
    token = fields.Char(copy=False, groups='base.group_system')
    enabled = fields.Boolean(default=False)
    days = fields.Integer(default=60, required=True)
    last_run = fields.Datetime(readonly=True)
    last_result = fields.Text(readonly=True)
    _company_unique = models.Constraint('UNIQUE(company_id)', 'Solo una configuración por empresa.')

    @api.constrains('days','company_id','enabled')
    def _check_config(self):
        for r in self:
            if not 1 <= r.days <= 366 or r.company_id.currency_id.name != 'CLP' or r.company_id.parent_id:
                raise ValidationError('Se requiere empresa raíz CLP y rango de 1 a 366 días.')
            if r.enabled and r.company_id.currency_interval_unit != 'manually':
                raise ValidationError('Desactive primero la actualización estándar de monedas (Manual).')

    def _fetch(self, code, start, end):
        self.ensure_one()
        if not self.token:
            raise UserError('Configure el token BCCh.')
        try:
            response = requests.get(URL, params={'token':self.token.strip(),'function':'GetSeries','timeseries':SERIES[code],'firstdate':str(start),'lastdate':str(end)}, timeout=(10,30), allow_redirects=False)
            if response.status_code != 200:
                raise ValueError('HTTP')
            data = response.json()
            series = data.get('Series') or {}
            if str(data.get('Codigo')) != '0' or series.get('seriesId') != SERIES[code]:
                raise ValueError('API')
            obs = series['Obs']
            if not isinstance(obs,list) or not obs:
                raise ValueError('Observaciones')
            result = {}
            for item in obs:
                day = datetime.strptime(item['indexDateString'],'%d-%m-%Y').date()
                if not start <= day <= end:
                    raise ValueError('Fecha')
                if item.get('statusCode') != 'OK':
                    continue
                value = Decimal(str(item['value']))
                if not value.is_finite() or value <= 0 or day in result:
                    raise ValueError('Valor')
                result[day] = value
            return result
        except Exception:
            raise UserError('Error de consulta o validación BCCh para %s. Revise conexión y token.' % code) from None

    def _run(self, apply=False):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM agrusa_currency_sync WHERE id=%s FOR UPDATE', [self.id])
        today = datetime.now(TZ).date()
        start = today - timedelta(days=self.days-1)
        counts = dict(iguales=0,faltantes=0,creadas=0,diferentes=0)
        details = []
        status = 'ok'
        try:
            with self.env.cr.savepoint():
                self._check_config()
                if apply and self.company_id.currency_interval_unit != 'manually':
                    raise UserError('Desactive la actualización estándar antes de registrar tasas.')
                rates = self.env['res.currency.rate'].with_company(self.company_id)
                for code in SERIES:
                    currency = self.env['res.currency'].search([('name','=',code)],limit=1)
                    if not currency:
                        raise UserError('Moneda activa no encontrada: %s' % code)
                    for day,value in sorted(self._fetch(code,start,today).items()):
                        existing = rates.search([('company_id','=',self.company_id.id),('currency_id','=',currency.id),('name','=',day)])
                        if len(existing)>1:
                            raise UserError('Tasas duplicadas: %s %s' % (code,day))
                        if not existing:
                            counts['faltantes'] += 1
                            details.append('%s %s faltante: %s' % (day,code,value))
                            if apply:
                                rates.create({'company_id':self.company_id.id,'currency_id':currency.id,'name':day,'inverse_company_rate':float(value)})
                                counts['creadas'] += 1
                        elif abs(Decimal(str(existing.inverse_company_rate))-value)<=Decimal('0.005'):
                            counts['iguales'] += 1
                        else:
                            counts['diferentes'] += 1
                            details.append('%s %s Odoo %.2f / BCCh %s' % (day,code,existing.inverse_company_rate,value))
        except Exception as exc:
            status = 'error'
            counts['creadas'] = 0
            details.append(str(exc) if isinstance(exc,UserError) else 'Error interno: '+type(exc).__name__)
        summary = ', '.join('%s: %s' % x for x in counts.items())
        if status == 'error':
            summary = 'ERROR - transacción de tasas revertida. '+summary
        self.env['agrusa.currency.sync.log'].create({'company_id':self.company_id.id,'mode':'apply' if apply else 'test','status':status,'summary':summary,'detail':'\n'.join(details)})
        self.write({'last_run':fields.Datetime.now(),'last_result':summary})
        return {'type':'ir.actions.client','tag':'display_notification','params':{'title':'Banco Central','message':summary,'type':'danger' if status=='error' else 'warning' if counts['diferentes'] else 'success','sticky':True}}

    def action_test(self):
        return self._run(False)

    def action_apply(self):
        return self._run(True)

    @api.model
    def _cron_sync(self):
        if self.env['ir.config_parameter'].sudo().get_param('database.is_neutralized') in ('True','true','1'):
            return
        now = datetime.now(TZ)
        if now.hour < 8:
            return
        for config in self.search([('enabled','=',True)]):
            last_log = self.env['agrusa.currency.sync.log'].search([('company_id','=',config.company_id.id),('mode','=','apply'),('status','=','ok')],limit=1)
            last = last_log.create_date
            if last and last.replace(tzinfo=ZoneInfo('UTC')).astimezone(TZ).date() == now.date():
                continue
            config._run(True)

class SyncLog(models.Model):
    _name = 'agrusa.currency.sync.log'
    _description = 'Historial BCCh'
    _order = 'id desc'
    company_id = fields.Many2one('res.company',required=True)
    mode = fields.Selection([('test','Prueba'),('apply','Actualización')],required=True)
    status = fields.Selection([('ok','Completado'),('error','Error')],required=True)
    summary = fields.Char()
    detail = fields.Text()
