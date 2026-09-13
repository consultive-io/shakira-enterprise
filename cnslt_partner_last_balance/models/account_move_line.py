from odoo import api, fields, models

from .res_partner import BALANCE_GROUPS


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

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
        """The Due of each line's own partner.

        On a journal entry the partner is per line rather than in the header --
        which is why ``account.move`` leaves its Last Balance at zero for an
        entry, and why the figure belongs here.

        Read once per partner and company. ``total_all_due`` is computed and not
        stored, and it is read through ``with_company``, so the same contact on
        twenty lines would otherwise be recomputed twenty times.
        """
        due_per_partner = {}
        for line in self:
            key = (line.partner_id.commercial_partner_id.id, line.company_id.id)
            if key not in due_per_partner:
                due_per_partner[key] = line.partner_id._get_last_balance(line.company_id)
            line.partner_last_balance = due_per_partner[key]
