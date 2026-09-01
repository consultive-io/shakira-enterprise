from collections import defaultdict

from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL

from .account_group import ACCOUNT_CODE_REGEX, MAX_ACCOUNT_CODE_LENGTH


class AccountAccount(models.Model):
    _inherit = 'account.account'

    coding_group_id = fields.Many2one(
        comodel_name='account.group',
        string="Coding Group",
        ondelete='restrict',
        check_company=False,
        tracking=True,
        help="Group driving the automatic generation of this account's code.",
    )
    coding_mode = fields.Selection(
        selection=[
            ('auto', "Automatic"),
            ('manual', "Manual"),
        ],
        string="Coding Mode",
        default='auto',
        required=True,
        help="Automatic: the code is generated from the coding group on creation.\n"
             "Manual: the code is entered by the user, as in standard Odoo.",
    )
    coding_next_code = fields.Char(
        string="Next Code",
        compute='_compute_coding_next_code',
        help="Preview of the code that would be allocated for the active company. "
             "The definitive code is allocated when the account is saved.",
    )
    caac_enforce_auto = fields.Boolean(
        string="Auto Coding Enforced",
        compute='_compute_caac_enforce_auto',
        help="Technical field driving the read-only state of the coding mode.",
    )

    # ------------------------------------------------------------------
    # Computes / onchanges
    # ------------------------------------------------------------------

    @api.depends_context('company')
    def _compute_caac_enforce_auto(self):
        enforced = self.env.company.root_id.caac_enforce_auto
        for account in self:
            account.caac_enforce_auto = enforced

    @api.depends('coding_group_id', 'coding_mode')
    @api.depends_context('company')
    def _compute_coding_next_code(self):
        for account in self:
            group = account.coding_group_id
            if account.coding_mode != 'auto' or not group:
                account.coding_next_code = False
                continue
            try:
                account.coding_next_code = self._caac_peek_code(
                    group, self.env.company.root_id, exclude_ids=account._origin.ids,
                )
            except ValidationError:
                account.coding_next_code = False

    @api.onchange('coding_group_id', 'coding_mode')
    def _onchange_coding_group_id(self):
        """Show a preview in the code field. The authoritative code is allocated
        under an advisory lock in ``create``."""
        if self.coding_mode != 'auto' or not self.coding_group_id:
            return
        if self._origin.id and self._origin.code:
            # Never silently rewrite the code of a saved account.
            return
        try:
            self.code = self._caac_peek_code(self.coding_group_id, self.env.company.root_id)
        except ValidationError:
            return

    # ------------------------------------------------------------------
    # Generation engine
    # ------------------------------------------------------------------

    @api.model
    def _caac_group_for_company(self, group, company):
        """Return the group of ``company``'s root that mirrors ``group``.

        Account groups belong to a root company. When an account spans several
        company trees, each tree has its own group records; they are matched on
        the starting code prefix.
        """
        company = company.root_id
        if group.company_id == company:
            return group
        return self.env['account.group'].search([
            ('company_id', '=', company.id),
            ('code_prefix_start', '=', group.code_prefix_start),
        ], limit=1)

    @api.model
    def _caac_resolve_group(self, code, company):
        """Return the group standard Odoo would attach to ``code``.

        Replicates the resolution used by ``_compute_account_group`` so we can
        assert the generated code lands back on the group the user picked.
        """
        rows = self.env.execute_query(SQL(
            """
            SELECT id
              FROM account_group
             WHERE company_id = %(company_id)s
               AND code_prefix_start <= LEFT(%(code)s, char_length(code_prefix_start))
               AND code_prefix_end >= LEFT(%(code)s, char_length(code_prefix_end))
          ORDER BY char_length(code_prefix_start) DESC, id
             LIMIT 1
            """,
            company_id=company.root_id.id,
            code=code,
        ))
        return self.env['account.group'].browse(rows[0][0]) if rows else self.env['account.group']

    @api.model
    def _caac_used_serials(self, prefix, width, company, exclude_ids=None):
        """Return the set of serials already taken under ``prefix`` in ``company``.

        ``exclude_ids`` drops specific accounts from the scan. It is used when
        reissuing a code so that a record's own current code is not counted as an
        obstacle to itself.
        """
        company = company.root_id
        total = len(prefix) + width
        # Flush so that codes written earlier in this transaction are visible.
        self.env['account.account'].flush_model(['code_store'])
        pattern = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        rows = self.env.execute_query(SQL(
            """
            SELECT code_store ->> %(company_key)s
              FROM account_account
             WHERE code_store ->> %(company_key)s LIKE %(pattern)s
               AND NOT (id = ANY(%(exclude_ids)s))
            """,
            company_key=str(company.id),
            pattern=pattern,
            exclude_ids=list(exclude_ids or []),
        ))
        serials = set()
        for (code,) in rows:
            if not code or len(code) != total or not code.startswith(prefix):
                continue
            suffix = code[len(prefix):]
            if suffix.isdigit():
                serials.add(int(suffix))
        return serials

    @api.model
    def _caac_build_code(self, group, company, cache=None, lock=False, exclude_ids=None):
        """Core allocation routine. Returns the next code for ``group`` in ``company``.

        :param cache: set of codes already handed out in this transaction but not
                      yet flushed (batch creation).
        :param lock: take a transaction-level advisory lock on (company, prefix).
                     Always True on the authoritative path, False for previews.
        :param exclude_ids: accounts whose existing codes must be ignored, so that a
                            record being reissued does not block itself.
        """
        company = company.root_id
        prefix = group._caac_effective_prefix()
        if not prefix:
            raise ValidationError(_(
                "Group %(group)s has no code prefix, so no account code can be generated "
                "from it.", group=group.display_name,
            ))
        if not ACCOUNT_CODE_REGEX.match(prefix):
            raise ValidationError(_(
                "The coding prefix %(prefix)s can only contain alphanumeric characters "
                "and dots.", prefix=prefix,
            ))

        width = group._caac_effective_width(company)
        total = len(prefix) + width
        if total > MAX_ACCOUNT_CODE_LENGTH:
            raise ValidationError(_(
                "Prefix %(prefix)s with a serial width of %(width)s would produce codes "
                "longer than %(maximum)s characters.",
                prefix=prefix, width=width, maximum=MAX_ACCOUNT_CODE_LENGTH,
            ))

        if lock:
            # Transaction-level lock: released on commit/rollback. Serialises
            # allocation per (root company, prefix) without blocking other prefixes.
            self.env.execute_query(SQL(
                "SELECT pg_advisory_xact_lock(%(company_id)s, hashtext(%(prefix)s))",
                company_id=company.id,
                prefix=prefix,
            ))

        serials = self._caac_used_serials(prefix, width, company, exclude_ids=exclude_ids)
        for code in (cache or ()):
            if len(code) == total and code.startswith(prefix) and code[len(prefix):].isdigit():
                serials.add(int(code[len(prefix):]))

        ceiling = 10 ** width - 1
        next_serial = (max(serials) if serials else 0) + 1
        if next_serial > ceiling:
            raise ValidationError(_(
                "Prefix %(prefix)s is exhausted: all %(ceiling)s serials are in use. "
                "Widen the serial for this group, or split it into sub-groups.",
                prefix=prefix, ceiling=ceiling,
            ))

        code = f"{prefix}{next_serial:0{width}d}"

        resolved = self._caac_resolve_group(code, company)
        expected = self._caac_group_for_company(group, company)
        if expected and resolved != expected:
            raise ValidationError(_(
                "The generated code %(code)s would be reported under group %(resolved)s "
                "instead of %(expected)s. A child group's prefix range overlaps the "
                "generated serials — narrow the prefix or adjust the serial width.",
                code=code,
                resolved=resolved.display_name or _("no group"),
                expected=expected.display_name,
            ))
        return code

    @api.model
    def _caac_peek_code(self, group, company, exclude_ids=None):
        """Non-locking preview. May be superseded by a concurrent allocation."""
        return self._caac_build_code(group, company, lock=False, exclude_ids=exclude_ids)

    @api.model
    def _caac_allocate_code(self, group, company, cache=None, exclude_ids=None):
        """Authoritative, lock-protected allocation."""
        return self._caac_build_code(
            group, company, cache=cache, lock=True, exclude_ids=exclude_ids,
        )

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def _caac_target_companies(self, vals):
        """Mirror core's company resolution in ``account.account.create``."""
        company_ids = self._fields['company_ids'].convert_to_cache(
            vals.get('company_ids', []), self.browse(),
        )
        companies = self.env['res.company'].browse(company_ids)
        if self.env.company in companies or not companies:
            companies = self.env.company | companies
        return companies

    def _caac_prepare_create_vals(self, vals, cache):
        if vals.get('coding_mode', 'auto') != 'auto':
            return
        group_id = vals.get('coding_group_id')
        if not group_id:
            return
        if 'prefix' in vals:
            # Core's own chart-template shortcut; leave it alone.
            return

        group = self.env['account.group'].browse(group_id)
        companies = self._caac_target_companies(vals)
        mapping_commands = list(vals.get('code_mapping_ids') or [])

        for index, company in enumerate(companies):
            root = company.root_id
            company_group = self._caac_group_for_company(group, root) or group
            code = self.with_company(root)._caac_allocate_code(
                company_group, root, cache=cache[root.id],
            )
            cache[root.id].add(code)
            if index == 0:
                vals['code'] = code
            else:
                mapping_commands.append(Command.create({
                    'company_id': company.id,
                    'code': code,
                }))

        if len(companies) > 1:
            vals['code_mapping_ids'] = mapping_commands

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('caac_no_autocode') and not self.env.context.get('import_file'):
            cache = defaultdict(set)
            for vals in vals_list:
                self._caac_prepare_create_vals(vals, cache)
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_caac_regenerate_code(self):
        """Re-issue the code from the coding group.

        Deliberately refused once the account carries journal items: renumbering a
        posted account is an audit decision, not a technical one.
        """
        cache = defaultdict(set)
        for account in self:
            if account.coding_mode != 'auto' or not account.coding_group_id:
                raise UserError(_(
                    "Account %(account)s is not on automatic coding.",
                    account=account.display_name,
                ))
            if account.used:
                raise UserError(_(
                    "Account %(account)s already has journal items; its code cannot be "
                    "regenerated.", account=account.display_name,
                ))
            for company in account.company_ids:
                root = company.root_id
                group = self._caac_group_for_company(account.coding_group_id, root) \
                    or account.coding_group_id
                code = account.with_company(root)._caac_allocate_code(
                    group, root, cache=cache[root.id], exclude_ids=account.ids,
                )
                cache[root.id].add(code)
                account.with_company(root).code = code
        return True
