# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.videovision_customer_cheques.tests.common import VvAccountCommon


@tagged('post_install', '-at_install')
class TestCreditInvoice(VvAccountCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner.write({'vv_credit_policy': 'limit', 'vv_credit_limit': 1000.0})
        cls.storable = cls.env['product.product'].create({
            'name': 'Cámara IP', 'type': 'consu', 'is_storable': True, 'list_price': 100.0,
            'invoice_policy': 'order', 'taxes_id': [(5, 0, 0)]})
        cls.service = cls.env['product.product'].create({
            'name': 'Instalación', 'type': 'service', 'list_price': 100.0, 'invoice_policy': 'order',
            'taxes_id': [(5, 0, 0)]})
        cls.seller = cls.env['res.users'].create({
            'name': 'Vendedor Crédito', 'login': 'vend_credito_inv',
            'group_ids': [(6, 0, [cls.env.ref('sales_team.group_sale_salesman_all_leads').id,
                                  cls.env.ref('account.group_account_invoice').id])],
        })

    def _order(self, amount, partner=None, product=None, qty=1):
        product = product or self.service
        product.list_price = amount
        order = self.env['sale.order'].create({
            'partner_id': (partner or self.partner).id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty,
                                   'price_unit': amount, 'tax_ids': [(5, 0, 0)]})],
        })
        return order

    def _invoice_order(self, order, user=None, **wiz_vals):
        wiz = self.env['sale.advance.payment.inv'].with_user(user or self.env.user).with_context(
            active_model='sale.order', active_ids=order.ids, active_id=order.id).create(
            dict({'advance_payment_method': 'delivered'}, **wiz_vals))
        return wiz.create_invoices()

    def test_confirm_never_blocks_and_reserves(self):
        self._invoice(100, days_ago=60, due_days=30)  # moroso
        order = self._order(5000, product=self.storable)
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertTrue(order.picking_ids)
        # 12-nov: confirma y reserva igual, pero queda pendiente de aprobación de inmediato
        self.assertEqual(order.vv_credit_state, 'pending')

    def test_over_limit_blocks_invoice_then_approval_covers_all_invoices(self):
        order = self._order(1500, qty=2)  # 3000 > 1000
        order.action_confirm()
        res = self._invoice_order(order, user=self.seller)
        self.assertEqual(res['tag'], 'display_notification')
        self.assertFalse(order.invoice_ids)
        self.assertEqual(order.vv_credit_state, 'pending')
        self.assertEqual(order.vv_credit_block_reason, 'limit')
        self.assertEqual(order.vv_credit_pending_amount, 3000)
        with self.assertRaisesRegex(UserError, 'Aprobar pedidos'):
            order.with_user(self.seller)._vv_credit_approve()
        order._vv_credit_approve('Cliente histórico')
        self.assertEqual(order.vv_credit_state, 'approved')
        res = self._invoice_order(order, user=self.seller)
        self.assertEqual(len(order.invoice_ids), 1)
        order.invoice_ids.with_user(self.seller).action_post()
        self.assertEqual(order.invoice_ids.state, 'posted')

    def test_downpayment_blocked(self):
        order = self._order(1500)
        order.action_confirm()
        self._invoice_order(order, advance_payment_method='fixed', fixed_amount=1200)
        self.assertFalse(order.invoice_ids)
        self.assertEqual(order.vv_credit_state, 'pending')
        self.assertFalse(order.order_line.filtered('is_downpayment'))

    def test_overdue_blocks_invoice(self):
        self._invoice(100, days_ago=60, due_days=30)
        order = self._order(100)
        order.action_confirm()
        self._invoice_order(order)
        self.assertEqual(order.vv_credit_block_reason, 'overdue')

    def test_within_limit_invoices_and_orders_not_counted(self):
        o1 = self._order(800)
        o1.action_confirm()
        o2 = self._order(800)
        o2.action_confirm()  # pedidos por facturar ya no ocupan cupo
        snap = self.partner._vv_credit_snapshot()
        self.assertEqual(snap['exposure'], 0)
        self.assertEqual(snap['orders'], 0)
        self._invoice_order(o2)
        self.assertEqual(len(o2.invoice_ids), 1)
        o2.invoice_ids.action_post()
        self._invoice_order(o1)  # 800 + 800 > 1000
        self.assertEqual(o1.vv_credit_state, 'pending')

    def test_post_recheck_old_draft(self):
        order = self._order(500)
        order.action_confirm()
        self._invoice_order(order)
        draft = order.invoice_ids
        self.assertEqual(draft.state, 'draft')
        # el cliente cae en mora antes de publicar el borrador
        self._invoice(100, days_ago=60, due_days=30)
        res = draft.action_post()
        self.assertEqual(draft.state, 'draft')
        self.assertEqual(res['tag'], 'display_notification')
        self.assertEqual(order.vv_credit_state, 'pending')
        with self.assertRaises(UserError):
            draft._post()
        order._vv_credit_approve()
        draft.action_post()
        self.assertEqual(draft.state, 'posted')

    def test_approval_invalid_when_order_grows(self):
        order = self._order(1500)
        order.action_confirm()
        self._invoice_order(order)
        order._vv_credit_approve()
        self.assertTrue(order._vv_credit_approval_valid())
        order.with_context(vv_skip_sale_order_lock=True).order_line.product_uom_qty = 2
        self.assertFalse(order._vv_credit_approval_valid())
        self._invoice_order(order)
        self.assertEqual(order.vv_credit_state, 'pending')

    def test_paid_customer_clears_pending(self):
        inv = self._invoice(900, days_ago=60, due_days=30)
        order = self._order(100)
        order.action_confirm()
        self._invoice_order(order)
        self.assertEqual(order.vv_credit_state, 'pending')
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=inv.ids).create({
                'journal_id': self.bank_journal.id})._create_payments()
        self._invoice_order(order)
        self.assertEqual(order.vv_credit_state, 'auto')
        self.assertEqual(len(order.invoice_ids), 1)

    def test_direct_invoice_needs_approver(self):
        self._invoice(100, days_ago=60, due_days=30)
        inv = self.env['account.move'].with_context(vv_skip_invoice_mirror=True).create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.product.id, 'quantity': 1, 'price_unit': 50,
                                         'tax_ids': [(5, 0, 0)]})]})
        with self.assertRaisesRegex(UserError, 'aprobador'):
            inv.with_user(self.seller).with_context(vv_skip_invoice_mirror=True).action_post()
        inv.with_context(vv_skip_invoice_mirror=True).action_post()  # admin es aprobador
        self.assertEqual(inv.state, 'posted')
        self.assertEqual(inv.vv_credit_override_by, self.env.user)

    def test_reserved_credit_issue_filter(self):
        self.env['stock.quant']._update_available_quantity(
            self.storable, self.env['stock.warehouse'].search([('company_id', '=', self.company.id)], limit=1).lot_stock_id, 10)
        order = self._order(100, product=self.storable)
        order.action_confirm()
        self.assertNotIn(order, self.env['sale.order'].search([('vv_reserved_credit_issue', '=', True)]))
        self._invoice(100, days_ago=60, due_days=30)
        self.assertIn(order, self.env['sale.order'].search([('vv_reserved_credit_issue', '=', True)]))

    def test_seller_sees_but_cannot_edit_tolerances(self):
        partner = self.partner.with_user(self.seller)
        self.assertFalse(partner.vv_credit_is_manager)
        self.assertEqual(partner.vv_credit_overdue_tolerance_days, 0)
        with self.assertRaises(UserError):
            partner.vv_credit_overdue_tolerance_days = 5

    # ---- Reunión 12-nov ----
    def test_confirm_puts_order_pending_immediately(self):
        order = self._order(1500, qty=2)  # 3000 > línea 1000
        order.with_user(self.seller).action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.vv_credit_state, 'pending')
        self.assertEqual(order.vv_credit_block_reason, 'limit')
        pending = self.env['sale.order'].search([('vv_credit_state', '=', 'pending'), ('id', '=', order.id)])
        self.assertEqual(pending, order)

    def test_confirm_within_limit_not_pending(self):
        order = self._order(500)
        order.action_confirm()
        self.assertNotEqual(order.vv_credit_state, 'pending')

    def test_daily_review_holds_and_releases(self):
        order = self._order(500)
        order.action_confirm()
        self.assertNotEqual(order.vv_credit_state, 'pending')
        inv = self._invoice(100, days_ago=60, due_days=30)  # el cliente cae en mora
        self.env['sale.order']._vv_cron_credit_review()
        self.assertEqual(order.vv_credit_state, 'pending')
        self.assertEqual(order.vv_credit_block_reason, 'overdue')
        # paga la factura vencida: la revisión diaria libera el pedido
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=inv.ids).create(
            {'journal_id': self.bank_journal.id})._create_payments()
        self.env['sale.order']._vv_cron_credit_review()
        self.assertEqual(order.vv_credit_state, 'auto')

    def test_events_refresh_credit_without_daily_review(self):
        """Reunión 19-nov (C2): sin esperar la revisión diaria."""
        order = self._order(500)
        order.action_confirm()
        self.assertNotEqual(order.vv_credit_state, 'pending')
        inv = self._invoice(100, days_ago=60, due_days=30)  # registrar una factura vencida
        self.assertEqual(order.vv_credit_state, 'pending', "Al registrar la factura el pedido queda retenido")
        self.assertEqual(order.vv_credit_block_reason, 'overdue')
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=inv.ids).create(
            {'journal_id': self.bank_journal.id})._create_payments()
        self.assertEqual(order.vv_credit_state, 'auto', "Al pagar y conciliar se libera solo")

    def test_new_order_reviews_other_orders(self):
        order = self._order(500)
        order.action_confirm()
        self.assertNotEqual(order.vv_credit_state, 'pending')
        # Mora registrada sin pasar por _post (por ejemplo, carga sin recálculo): el pedido sigue libre
        self._invoice(100, days_ago=60, due_days=30)
        order.vv_credit_state = 'auto'
        order2 = self._order(200)
        order2.action_confirm()
        self.assertEqual(order.vv_credit_state, 'pending', "Un pedido nuevo revisa los otros pedidos del cliente")
