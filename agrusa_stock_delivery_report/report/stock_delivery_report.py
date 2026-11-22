from odoo import api, models, _
from odoo.exceptions import UserError


class ReportStockDeliveryNoValues(models.AbstractModel):
    _name = 'report.agrusa_stock_delivery_report.delivery_nv'
    _description = 'AGRUSA - Documento de entrega o traslado sin valores'

    @api.model
    def _get_report_values(self, docids, data=None):
        pickings = self.env['stock.picking'].browse(docids).exists()
        if not pickings:
            raise UserError(_('No se encontraron transferencias para imprimir.'))
        invalid = pickings.filtered(lambda p: p.picking_type_id.code not in ('outgoing', 'internal'))
        if invalid:
            raise UserError(_('Este documento solo se imprime para salidas y traslados internos.'))
        return {'doc_ids': pickings.ids, 'doc_model': 'stock.picking', 'docs': pickings}
