from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .caac_account_type import TYPE_CODE_LENGTH

# The group serial is fixed at three digits: the change request specifies a
# five-character group code, and the type code takes the other two.
GROUP_SERIAL_WIDTH = 3
GROUP_CODE_LENGTH = TYPE_CODE_LENGTH + GROUP_SERIAL_WIDTH


class AccountGroup(models.Model):
    _name = 'account.group'
    _inherit = ['account.group', 'caac.serial.allocator.mixin']

    caac_account_type_id = fields.Many2one(
        comodel_name='caac.account.type',
        string="Account Type",
        ondelete='restrict',
        help="Selecting a type generates this group's code prefix as "
             "<type code><serial>, and locks it against editing.",
    )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _caac_type_code(self, account_type, company):
        """Return the type's two-digit code in ``company``, or raise."""
        code = account_type.with_company(company.root_id).code
        if not code:
            raise ValidationError(_(
                "Account type %(type)s has no code for %(company)s yet. Set its "
                "%(length)s-digit code under Accounting > Configuration > Account Type "
                "Coding before creating groups from it.",
                type=account_type.name,
                company=company.root_id.display_name,
                length=TYPE_CODE_LENGTH,
            ))
        return code

    def _caac_used_group_serials(self, prefix, company, exclude_ids=None):
        """Serials already taken by groups under ``prefix`` in ``company``.

        ``exclude_ids`` drops a group from the scan so that re-coding a record does
        not treat its own prefix as an obstacle to itself.
        """
        total = len(prefix) + GROUP_SERIAL_WIDTH
        # Flush so that prefixes written earlier in this transaction are visible.
        self.env['account.group'].flush_model(['code_prefix_start'])
        domain = [
            ('company_id', '=', company.root_id.id),
            ('code_prefix_start', '=like', f'{prefix}%'),
        ]
        if exclude_ids:
            domain.append(('id', 'not in', list(exclude_ids)))
        serials = set()
        for group in self.env['account.group'].sudo().search(domain):
            code = group.code_prefix_start or ''
            if len(code) != total or not code.startswith(prefix):
                continue
            suffix = code[len(prefix):]
            if suffix.isdigit():
                serials.add(int(suffix))
        return serials

    def _caac_generate_group_prefix(self, account_type, company, cache=None, exclude_ids=None):
        """Allocate the next group code under ``account_type`` in ``company``."""
        company = company.root_id
        prefix = self._caac_type_code(account_type, company)
        self._caac_lock_prefix(company, prefix)
        used = self._caac_used_group_serials(prefix, company, exclude_ids=exclude_ids)
        serial = self._caac_next_serial(prefix, GROUP_SERIAL_WIDTH, used, cache=cache)
        return self._caac_format_code(prefix, GROUP_SERIAL_WIDTH, serial)

    def _caac_prefix_vals(self, prefix):
        """The three fields a generated group code has to land on.

        ``code_prefix_start`` and ``code_prefix_end`` are what core resolves accounts
        against, and carry a database constraint that both be the same length.
        ``coding_prefix`` is what consultive_coa_auto_coding_basic issues account
        codes from.
        """
        return {
            'code_prefix_start': prefix,
            'code_prefix_end': prefix,
            'coding_prefix': prefix,
        }

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _caac_has_accounts(self):
        """Whether any account has been issued a code under this group's prefix.

        ``group_id`` on account.account is a non-stored compute with no search, so
        the prefix is what can actually be queried.
        """
        self.ensure_one()
        if not self.code_prefix_start:
            return False
        return bool(
            self.env['account.account'].sudo()
            .with_company(self.company_id.root_id)
            .with_context(active_test=False)
            .search_count([('code', '=like', f'{self.code_prefix_start}%')], limit=1)
        )

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        cache = defaultdict(set)
        for vals in vals_list:
            type_id = vals.get('caac_account_type_id')
            if not type_id:
                continue
            account_type = self.env['caac.account.type'].browse(type_id)
            company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
            prefix = self._caac_generate_group_prefix(
                account_type, company, cache=cache[company.root_id.id],
            )
            cache[company.root_id.id].add(prefix)
            vals.update(self._caac_prefix_vals(prefix))
        return super().create(vals_list)

    def write(self, vals):
        if not vals.get('caac_account_type_id'):
            return super().write(vals)

        account_type = self.env['caac.account.type'].browse(vals['caac_account_type_id'])
        # Each record needs its own generated prefix, so a multi-record write of a
        # type change cannot share one vals dict.
        if len(self) > 1:
            for group in self:
                group.write(vals)
            return True

        self.ensure_one()
        if self.caac_account_type_id == account_type:
            return super().write(vals)
        if self._caac_has_accounts():
            raise UserError(_(
                "Group %(group)s already has accounts coded under %(prefix)s, so its "
                "account type cannot be changed. Those accounts would keep a code that no "
                "longer matches their group.",
                group=self.display_name, prefix=self.code_prefix_start,
            ))
        prefix = self._caac_generate_group_prefix(
            account_type, self.company_id, exclude_ids=self.ids,
        )
        return super().write({**vals, **self._caac_prefix_vals(prefix)})

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('caac_account_type_id', 'code_prefix_start', 'code_prefix_end')
    def _check_caac_group_code(self):
        for group in self:
            if not group.caac_account_type_id:
                continue
            if len(group.code_prefix_start or '') != GROUP_CODE_LENGTH:
                raise ValidationError(_(
                    "Group %(group)s is coded from an account type, so its code prefix must "
                    "be exactly %(length)s characters. It is \"%(prefix)s\".",
                    group=group.name,
                    length=GROUP_CODE_LENGTH,
                    prefix=group.code_prefix_start or '',
                ))
