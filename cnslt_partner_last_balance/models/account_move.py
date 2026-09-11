from odoo import api, fields, models

from .res_partner import BALANCE_GROUPS


class AccountMove(models.Model):
    _inherit = 'account.move'

    partner_last_balance = fields.Monetary(
        string="Last Balance",
        compute='_compute_partner_last_balance',
        currency_field='company_currency_id',
        groups=BALANCE_GROUPS,
        help="The partner's Due, exactly as on the contact: what they owe you "
             "minus what you owe them, from posted entries not yet reconciled. "
             "Negative means you owe them.",
    )

    @api.depends('partner_id', 'company_id', 'move_type')
    def _compute_partner_last_balance(self):
        for move in self:
            # A journal entry has no customer or vendor side to speak of.
            if move.move_type == 'entry':
                move.partner_last_balance = 0.0
            else:
                move.partner_last_balance = move.partner_id._get_last_balance(move.company_id)
