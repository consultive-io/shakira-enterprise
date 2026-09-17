from odoo import api, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        """Classify the contact Odoo creates behind a new company.

        ``res.company`` creates it inside ``create`` itself -- the company row
        cannot exist without one -- so there is no hook of its own to override.
        The context is how ``res.partner`` learns the contact it is about to
        create belongs to a company and should take the pair designated for
        Companies. A branch is created through the same path, so a branch's
        contact is classified the same way as its parent's.

        A company set up on a contact that already exists passes ``partner_id``,
        so core creates none and the code already issued to that contact is left
        alone.
        """
        companies = super(
            ResCompany, self.with_context(partner_code_designation='company')
        ).create(vals_list)
        # Hand the records back in the caller's environment: the designation
        # must not leak into whatever the caller does with them next.
        return companies.with_env(self.env)
