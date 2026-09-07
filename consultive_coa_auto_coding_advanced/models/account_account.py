from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    caac_account_type_id = fields.Many2one(
        comodel_name='caac.account.type',
        string="Account Type",
        ondelete='restrict',
        tracking=True,
        help="Selecting a type here fills the standard Account Type below it, and is "
             "what the coding groups are organised by.",
    )

    @api.onchange('caac_account_type_id')
    def _onchange_caac_account_type_id(self):
        if self.caac_account_type_id:
            self.account_type = self.caac_account_type_id.account_type

    @api.onchange('account_type')
    def _onchange_account_type(self):
        """Keep the technical wrapper in sync with Odoo's native selector.

        The form deliberately presents ``account_type`` with Odoo's grouped
        ``account_type_selection`` widget.  The wrapper remains stored because
        group coding uses it, but it should not force users through a plain
        Many2one dropdown.
        """
        if not self.account_type:
            self.caac_account_type_id = False
            return
        self.caac_account_type_id = self.env['caac.account.type'].search(
            [('account_type', '=', self.account_type)], limit=1,
        )

    @api.onchange('coding_group_id')
    def _onchange_caac_coding_group_id(self):
        """Preview the standard Odoo group as soon as a coding group is picked.

        ``group_id`` is a non-stored core compute based on ``code``.  The base
        auto-coding module fills a preview code in its own onchange, and the
        definitive generated code resolves to this same group when saved.  Set
        it here as well so the standard Group field immediately reflects the
        user's Coding Group choice, including on an existing account whose code
        has not yet been regenerated.
        """
        for account in self:
            if (
                account.coding_mode == 'auto'
                and account.coding_group_id
            ):
                account.group_id = account.coding_group_id

    @api.depends_context('company')
    @api.depends('code', 'coding_group_id')
    def _compute_account_group(self):
        """Use the selected coding group when a legacy code has no group.

        Odoo's normal code-prefix resolution remains authoritative whenever it
        finds a group.  The fallback keeps the standard Group useful for an
        existing account such as ``101000`` that has been put on automatic
        coding but whose old code does not belong to any account-group range.
        It also persists across reloads, unlike an onchange-only preview.
        """
        super()._compute_account_group()
        company = self.env.company.root_id
        for account in self.filtered(lambda record: not record.group_id and record.coding_group_id):
            account.group_id = self._caac_group_for_company(
                account.coding_group_id, company,
            ) or account.coding_group_id

    @api.model_create_multi
    def create(self, vals_list):
        # Fill the standard type from the wrapper so programmatic creation behaves
        # like the form. Deliberately only when account_type was not supplied: core's
        # _compute_account_type infers it from the code prefix during chart-template
        # installation, and that path has to keep working untouched.
        for vals in vals_list:
            type_id = vals.get('caac_account_type_id')
            if type_id and not vals.get('account_type'):
                vals['account_type'] = self.env['caac.account.type'].browse(type_id).account_type
        return super().create(vals_list)
