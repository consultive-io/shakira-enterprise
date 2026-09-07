import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TYPE_CODE_LENGTH = 2
TYPE_CODE_REGEX = re.compile(r'^[0-9]{2}$')

# Reading order of core's ``account_type_selection`` widget, which sorts the
# selection into Balance Sheet then Profit & Loss by matching the start of each
# value (see account/static/src/components/account_type_selection). The widget only
# binds to Selection fields, so this dropdown is a plain Many2one; mirroring the
# order here is what keeps it familiar to read.
GROUP_ORDER = ('asset', 'liability', 'equity', 'income', 'expense', 'off_balance')


def account_type_selection(env):
    """The live ``account.account.account_type`` selection.

    Read from the field rather than copied, so values added by Odoo or by another
    module appear here without this module being touched.
    """
    return env['account.account']._fields['account_type']._description_selection(env)


def ordered_account_types(env):
    """Selection values in the order core's type widget displays them."""
    selection = account_type_selection(env)
    ordered = []
    for prefix in GROUP_ORDER:
        ordered.extend(value for value, _label in selection if value.startswith(prefix))
    # Anything a future version adds outside the known groups still gets a place.
    ordered.extend(value for value, _label in selection if value not in ordered)
    return ordered


class CaacAccountType(models.Model):
    """A record per standard account type, so a code can be attached to it.

    ``account.account.account_type`` is a Selection, so there is nowhere to store a
    code against it. This model mirrors that selection one-for-one and carries the
    two-digit code that every account group code starts with.
    """
    _name = 'caac.account.type'
    _description = "Account Type Coding"
    _order = 'sequence, name'

    _account_type_uniq = models.Constraint(
        'unique(account_type)',
        "Each account type can only be configured once.",
    )

    name = fields.Char(required=True, translate=True)
    account_type = fields.Selection(
        selection=lambda self: account_type_selection(self.env),
        string="Account Type",
        required=True,
        help="The standard Odoo account type this record carries a code for.",
    )
    code = fields.Char(
        string="Code",
        company_dependent=True,
        help="Two digits every account group code under this type starts with.\n"
             "Set once, per company. Groups cannot be coded from a type until it is set.",
    )
    sequence = fields.Integer(default=100)
    group_count = fields.Integer(
        string="Groups",
        compute='_compute_group_count',
        help="Account groups already coded from this type in the active company.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('name')
    def _compute_display_name(self):
        for record in self:
            # The code is an implementation detail used to build account numbers,
            # not part of the accounting type's label.  Keeping the display name
            # equal to Odoo's native selection label also makes it safe to use in
            # regular Many2one contexts without exposing a company-specific code.
            record.display_name = record.name

    @api.depends_context('company')
    def _compute_group_count(self):
        counts = dict(self.env['account.group']._read_group(
            [('caac_account_type_id', 'in', self.ids),
             ('company_id', '=', self.env.company.root_id.id)],
            groupby=['caac_account_type_id'],
            aggregates=['__count'],
        ))
        for record in self:
            record.group_count = counts.get(record, 0)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('code')
    def _check_code(self):
        for record in self:
            if not record.code:
                continue
            if not TYPE_CODE_REGEX.match(record.code):
                raise ValidationError(_(
                    "The code of %(type)s must be exactly %(length)s digits, so that every "
                    "group code below it comes out the same length. \"%(code)s\" is not.",
                    type=record.name, length=TYPE_CODE_LENGTH, code=record.code,
                ))
            duplicate = self.search([('code', '=', record.code), ('id', '!=', record.id)], limit=1)
            if duplicate:
                raise ValidationError(_(
                    "Code %(code)s is already used by %(other)s in this company. Two account "
                    "types cannot share a code, or their group codes would collide.",
                    code=record.code, other=duplicate.name,
                ))

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _caac_code_is_in_use(self):
        """Whether groups have already been coded from this type in this company."""
        self.ensure_one()
        return bool(self.env['account.group'].sudo().search_count([
            ('caac_account_type_id', '=', self.id),
            ('company_id', '=', self.env.company.root_id.id),
        ], limit=1))

    def write(self, vals):
        if 'code' in vals:
            for record in self:
                if record.code and record.code != vals['code'] and record._caac_code_is_in_use():
                    raise ValidationError(_(
                        "The code of %(type)s cannot be changed: account groups have already "
                        "been coded from it. Those groups, and every account under them, would "
                        "be left carrying a code that no longer matches their type.",
                        type=record.name,
                    ))
        return super().write(vals)

    def action_caac_view_groups(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Groups coded from %s", self.name),
            'res_model': 'account.group',
            'view_mode': 'list,form',
            'domain': [('caac_account_type_id', '=', self.id)],
        }
