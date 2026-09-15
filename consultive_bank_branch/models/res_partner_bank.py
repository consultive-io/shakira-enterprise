from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    branch_id = fields.Many2one(
        "res.bank.branch", string="Branch", index="btree_not_null"
    )
    # What the Branch picker offers: the chosen bank's branches, and nothing
    # until a bank is chosen.
    allowed_branch_ids = fields.Many2many(related="bank_id.branch_ids")

    @api.onchange("bank_id")
    def _onchange_bank_id_branch(self):
        """Drop a branch the newly chosen bank does not list.

        The picker's domain only filters what can be chosen next; without this,
        a branch picked under the previous bank would survive the switch.
        """
        if self.branch_id not in self.bank_id.branch_ids:
            self.branch_id = False

    @api.constrains("bank_id", "branch_id")
    def _check_branch_belongs_to_bank(self):
        """The branch has to be one the account's bank lists.

        The picker's domain is client-side: an import, an ORM write and the API
        never see it and arrive here instead.
        """
        for account in self:
            if (
                account.branch_id
                and account.branch_id not in account.bank_id.branch_ids
            ):
                raise ValidationError(
                    _(
                        'Branch "%(branch)s" is not a branch of %(bank)s.',
                        branch=account.branch_id.display_name,
                        bank=account.bank_id.display_name
                        or _("the account's bank (none is set)"),
                    )
                )
