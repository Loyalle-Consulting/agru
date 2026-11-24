# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Libera las cotizaciones retenidas con la lógica anterior (bloqueo al confirmar) y deja
    el crédito utilizado sin pedidos por facturar."""
    env['res.company'].search([]).write({'vv_credit_include_orders': False})
    held = env['sale.order'].search([('state', 'in', ('draft', 'sent')), ('vv_credit_state', 'in', ('pending', 'rejected'))])
    if held:
        held.activity_unlink(['mail.mail_activity_data_todo'])
        held.write({'vv_credit_state': 'none', 'vv_credit_block_reason': False})
        for order in held:
            order.message_post(body=env._(
                "Retención de crédito liberada: desde ahora el crédito se revisa al facturar, no al confirmar."))
