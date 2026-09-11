from odoo import api, fields, models

from .res_partner import BALANCE_GROUPS


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_last_balance = fields.Monetary(
        string="Last Balance",
        compute='_compute_partner_last_balance',
        currency_field='company_currency_id',
        groups=BALANCE_GROUPS,
        help="The vendor's Due, exactly as on the contact: what they owe you "
             "minus what you owe them, from posted entries not yet reconciled. "
             "Negative means you owe them.",
    )

    @api.depends('partner_id', 'company_id')
    def _compute_partner_last_balance(self):
        for order in self:
            order.partner_last_balance = order.partner_id._get_last_balance(order.company_id)
