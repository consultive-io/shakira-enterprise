from odoo import api, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """Classify the contact Odoo creates behind a new user.

        ``res.users`` delegates to ``res.partner`` through ``_inherits``, so the
        contact is created inside ``super()`` by the ORM, with no hook of its
        own. The context is how ``res.partner`` learns the contact it is about to
        create belongs to a user and should take the pair designated for Users.

        A user invited onto a contact that already exists passes ``partner_id``,
        so the ORM writes to that contact instead of creating one and its
        existing code is left alone.
        """
        users = super(
            ResUsers, self.with_context(partner_code_designation='user')
        ).create(vals_list)
        # Hand the records back in the caller's environment: the designation
        # must not leak into whatever the caller does with them next.
        return users.with_env(self.env)
