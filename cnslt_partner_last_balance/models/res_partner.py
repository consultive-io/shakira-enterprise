from odoo import models

# The groups core puts on total_all_due. A document's Last Balance carries the
# same ones, so nobody sees it on an order who could not see it on the contact.
BALANCE_GROUPS = 'account.group_account_readonly,account.group_account_invoice'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _get_last_balance(self, company):
        """The contact's Due amount, as a document in ``company`` should show it.

        Read from the commercial partner. account_followup matches move lines on
        the exact partner id, and receivable and payable lines are booked on the
        commercial entity -- so an order addressed to "Acme, John Doe" would read
        0 from John Doe while the Acme contact shows the real figure.

        Under the document's company rather than whichever one the user has
        active, because the Due is scoped to ``env.company`` and its branches.

        sudo so that a partner hidden by a record rule still yields its figure;
        the fields that display this carry BALANCE_GROUPS, which is the real
        gate.
        """
        partner = self.commercial_partner_id
        if not partner:
            return 0.0
        return partner.sudo().with_company(company).total_all_due
