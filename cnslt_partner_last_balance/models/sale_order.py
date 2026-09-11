from odoo import api, fields, models

from .res_partner import BALANCE_GROUPS


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # The Due is in company currency; the order's own currency_id follows the
    # pricelist and may be foreign, so it cannot carry this figure.
    partner_balance_currency_id = fields.Many2one(related='company_id.currency_id')
    partner_last_balance = fields.Monetary(
        string="Last Balance",
        compute='_compute_partner_last_balance',
        currency_field='partner_balance_currency_id',
        groups=BALANCE_GROUPS,
        help="The customer's Due, exactly as on the contact: what they owe you "
             "minus what you owe them, from posted entries not yet reconciled. "
             "Negative means you owe them.",
    )

    @api.depends('partner_id', 'company_id')
    def _compute_partner_last_balance(self):
        for order in self:
            order.partner_last_balance = order.partner_id._get_last_balance(order.company_id)
