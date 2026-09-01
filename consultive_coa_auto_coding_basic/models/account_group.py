import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Mirrors ACCOUNT_CODE_REGEX in odoo/addons/account/models/account_account.py (19.0).
ACCOUNT_CODE_REGEX = re.compile(r'^[A-Za-z0-9.]+$')

MAX_ACCOUNT_CODE_LENGTH = 64  # account.account.code is declared with size=64.


class AccountGroup(models.Model):
    _inherit = 'account.group'

    coding_prefix = fields.Char(
        string="Coding Prefix",
        compute='_compute_coding_prefix',
        store=True,
        readonly=False,
        precompute=True,
        help="Prefix used when generating account codes for this group.\n"
             "Defaults to the starting code prefix. Set it explicitly when the group "
             "covers a prefix range and codes should be issued under one specific prefix.",
    )
    coding_serial_width = fields.Integer(
        string="Serial Width",
        default=0,
        help="Number of trailing digits reserved for the running serial.\n"
             "Leave at 0 to use the company-wide default.",
    )
    coding_allowed = fields.Boolean(
        string="Allow Auto Coding",
        default=True,
        help="Uncheck to hide this group from the automatic coding selector. "
             "Typically unchecked on summary/parent groups that only aggregate children.",
    )
    coding_next_code = fields.Char(
        string="Next Code",
        compute='_compute_coding_next_code',
        help="Code that would be allocated next for the active company.",
    )

    @api.depends('code_prefix_start')
    def _compute_coding_prefix(self):
        for group in self:
            if not group.coding_prefix:
                group.coding_prefix = group.code_prefix_start

    def _compute_coding_next_code(self):
        account_model = self.env['account.account']
        for group in self:
            company = self.env.company.root_id
            if not group.coding_allowed or group.company_id != company:
                group.coding_next_code = False
                continue
            try:
                group.coding_next_code = account_model._caac_peek_code(group, company)
            except ValidationError:
                group.coding_next_code = False

    @api.constrains('coding_prefix', 'coding_serial_width')
    def _check_coding_settings(self):
        for group in self:
            if group.coding_prefix and not ACCOUNT_CODE_REGEX.match(group.coding_prefix):
                raise ValidationError(_(
                    "The coding prefix of group %(group)s can only contain alphanumeric "
                    "characters and dots.",
                    group=group.display_name,
                ))
            if group.coding_serial_width < 0 or group.coding_serial_width > 9:
                raise ValidationError(_(
                    "The serial width of group %(group)s must be between 0 (use company "
                    "default) and 9.",
                    group=group.display_name,
                ))

    def _caac_effective_prefix(self):
        """Return the prefix under which codes are issued for this group."""
        self.ensure_one()
        return (self.coding_prefix or self.code_prefix_start or '').strip()

    def _caac_effective_width(self, company):
        """Return the serial width for this group in ``company``."""
        self.ensure_one()
        return self.coding_serial_width or company.root_id.caac_serial_width or 3
