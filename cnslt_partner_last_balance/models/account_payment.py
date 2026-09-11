from odoo import api, fields, models

from .res_partner import BALANCE_GROUPS


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    partner_last_balance = fields.Monetary(
        string="Last Balance",
        compute='_compute_partner_last_balance',
        currency_field='company_currency_id',
        groups=BALANCE_GROUPS,
        help="The partner's Due, exactly as on the contact: what they owe you "
             "minus what you owe them, from posted entries not yet reconciled. "
             "Negative means you owe them.",
    )

    @api.depends('partner_id', 'company_id')
    def _compute_partner_last_balance(self):
        for payment in self:
            payment.partner_last_balance = payment.partner_id._get_last_balance(payment.company_id)
