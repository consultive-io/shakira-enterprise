from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.consultive_coa_auto_coding_advanced.hooks import _caac_sync_account_types
from odoo.addons.consultive_coa_auto_coding_advanced.models.caac_account_type import (
    account_type_selection,
)


@tagged('post_install', '-at_install')
class TestAccountTypeCoding(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_company = cls.env.company.root_id
        cls.root_company.caac_serial_width = 3

        cls.AccountType = cls.env['caac.account.type']
        cls.Group = cls.env['account.group']

        cls.type_expense = cls.AccountType.search([('account_type', '=', 'expense')])
        cls.type_expense.code = '06'
        cls.type_income = cls.AccountType.search([('account_type', '=', 'income')])
        cls.type_income.code = '04'

    def _new_group(self, name, account_type, **kwargs):
        values = {
            'name': name,
            'caac_account_type_id': account_type.id,
            'company_id': self.root_company.id,
        }
        values.update(kwargs)
        return self.Group.create(values)

    # -- seeding -------------------------------------------------------

    def test_every_account_type_is_seeded(self):
        values = {value for value, _label in account_type_selection(self.env)}
        seeded = set(self.AccountType.search([]).mapped('account_type'))
        self.assertEqual(seeded, values)

    def test_seeding_is_idempotent(self):
        before = self.AccountType.search_count([])
        self.assertEqual(_caac_sync_account_types(self.env), 0)
        self.assertEqual(self.AccountType.search_count([]), before)

    def test_seeded_order_follows_the_type_widget(self):
        ordered = self.AccountType.search([]).mapped('account_type')
        groups = [value.split('_')[0] for value in ordered]
        # off_balance splits to "off"; everything else keeps its group prefix.
        first_seen = []
        for group in groups:
            if group not in first_seen:
                first_seen.append(group)
        self.assertEqual(
            first_seen,
            ['asset', 'liability', 'equity', 'income', 'expense', 'off'],
        )

    # -- the code ------------------------------------------------------

    def test_code_must_be_two_digits(self):
        for invalid in ('6', '060', 'AB', '0A'):
            with self.subTest(code=invalid), self.assertRaises(ValidationError):
                self.AccountType.search([('account_type', '=', 'asset_cash')]).code = invalid

    def test_two_digit_code_is_accepted(self):
        account_type = self.AccountType.search([('account_type', '=', 'asset_cash')])
        account_type.code = '01'
        self.assertEqual(account_type.code, '01')

    def test_code_is_unique_within_a_company(self):
        with self.assertRaises(ValidationError):
            self.AccountType.search([('account_type', '=', 'asset_cash')]).code = '06'

    def test_same_code_allowed_in_another_company(self):
        other = self.setup_other_company()['company']
        self.type_income.with_company(other.root_id).code = '06'
        self.assertEqual(self.type_income.with_company(other.root_id).code, '06')
        self.assertEqual(self.type_income.with_company(self.root_company).code, '04')

    def test_code_cannot_change_once_groups_exist(self):
        self._new_group('Office Expense', self.type_expense)
        with self.assertRaises(ValidationError):
            self.type_expense.code = '07'

    # -- the account wrapper -------------------------------------------

    def test_wrapper_fills_account_type_on_create(self):
        account = self.env['account.account'].create({
            'name': 'Wrapped',
            'code': '06009999',
            'coding_mode': 'manual',
            'caac_account_type_id': self.type_expense.id,
        })
        self.assertEqual(account.account_type, 'expense')

    def test_wrapper_fills_account_type_via_onchange(self):
        form = Form(self.env['account.account'])
        form.name = 'Wrapped'
        form.caac_account_type_id = self.type_expense
        self.assertEqual(form.account_type, 'expense')

    def test_native_account_type_onchange_fills_wrapper(self):
        form = Form(self.env['account.account'])
        form.name = 'Native selection'
        form.account_type = 'expense'
        self.assertEqual(form.caac_account_type_id, self.type_expense)

    def test_coding_group_onchange_fills_standard_group(self):
        group = self._new_group('Office Expense', self.type_expense)
        form = Form(self.env['account.account'])
        form.name = 'Office supplies'
        form.account_type = 'expense'
        form.coding_group_id = group
        self.assertEqual(form.group_id, group)

    def test_coding_group_onchange_fills_standard_group_on_existing_account(self):
        group = self._new_group('Office Expense', self.type_expense)
        account = self.env['account.account'].create({
            'name': 'Existing account',
            'code': '99999',
            'coding_mode': 'manual',
            'account_type': 'expense',
        })
        form = Form(account)
        form.coding_mode = 'auto'
        form.coding_group_id = group
        self.assertEqual(form.group_id, group)

        account.coding_mode = 'auto'
        account.coding_group_id = group
        self.assertEqual(account.group_id, group)

    def test_account_type_stays_writable_without_a_wrapper(self):
        # The chart-template and import paths set account_type directly and must
        # keep working; core's _compute_account_type is deliberately not overridden.
        account = self.env['account.account'].create({
            'name': 'Direct',
            'code': '06009998',
            'coding_mode': 'manual',
            'account_type': 'liability_current',
        })
        self.assertEqual(account.account_type, 'liability_current')
        self.assertFalse(account.caac_account_type_id)

    def test_explicit_account_type_wins_over_the_wrapper(self):
        account = self.env['account.account'].create({
            'name': 'Both',
            'code': '06009997',
            'coding_mode': 'manual',
            'caac_account_type_id': self.type_expense.id,
            'account_type': 'liability_current',
        })
        self.assertEqual(account.account_type, 'liability_current')

    # -- group coding --------------------------------------------------

    def test_first_group_code_starts_at_one(self):
        group = self._new_group('Office Expense', self.type_expense)
        self.assertEqual(group.code_prefix_start, '06001')

    def test_group_serial_increments(self):
        first = self._new_group('Office Expense', self.type_expense)
        second = self._new_group('Factory Expense', self.type_expense)
        self.assertEqual(first.code_prefix_start, '06001')
        self.assertEqual(second.code_prefix_start, '06002')

    def test_group_code_lands_on_all_three_prefix_fields(self):
        group = self._new_group('Office Expense', self.type_expense)
        self.assertEqual(group.code_prefix_start, '06001')
        self.assertEqual(group.code_prefix_end, '06001')
        self.assertEqual(group.coding_prefix, '06001')

    def test_types_have_independent_group_serials(self):
        expense = self._new_group('Office Expense', self.type_expense)
        income = self._new_group('Product Sales', self.type_income)
        self.assertEqual(expense.code_prefix_start, '06001')
        self.assertEqual(income.code_prefix_start, '04001')

    def test_batch_group_creation_does_not_collide(self):
        groups = self.Group.create([
            {'name': f'Expense {index}',
             'caac_account_type_id': self.type_expense.id,
             'company_id': self.root_company.id}
            for index in range(3)
        ])
        self.assertEqual(
            groups.mapped('code_prefix_start'), ['06001', '06002', '06003'],
        )

    def test_group_without_a_type_is_untouched(self):
        group = self.Group.create({
            'name': 'Manual',
            'code_prefix_start': '77',
            'code_prefix_end': '77',
            'company_id': self.root_company.id,
        })
        self.assertEqual(group.code_prefix_start, '77')

    def test_uncoded_type_is_refused_with_a_clear_error(self):
        uncoded = self.AccountType.search([('account_type', '=', 'asset_prepayments')])
        self.assertFalse(uncoded.code)
        with self.assertRaises(ValidationError):
            self._new_group('Prepayments', uncoded)

    def test_group_serial_exhaustion_raises(self):
        # Park a group on the last serial rather than creating 999 of them.
        self.Group.create({
            'name': 'Last',
            'code_prefix_start': '06999',
            'code_prefix_end': '06999',
            'company_id': self.root_company.id,
        })
        with self.assertRaises(ValidationError):
            self._new_group('One too many', self.type_expense)

    def test_changing_group_type_recodes_it(self):
        group = self._new_group('Moved', self.type_expense)
        self.assertEqual(group.code_prefix_start, '06001')
        group.caac_account_type_id = self.type_income
        self.assertEqual(group.code_prefix_start, '04001')

    def test_group_type_cannot_change_once_accounts_exist(self):
        group = self._new_group('Office Expense', self.type_expense)
        self.env['account.account'].create({
            'name': 'Office supplies',
            'account_type': 'expense',
            'coding_group_id': group.id,
        })
        with self.assertRaises(UserError):
            group.caac_account_type_id = self.type_income

    # -- end to end ----------------------------------------------------

    def test_pdf_worked_example(self):
        office = self._new_group('Office Expense', self.type_expense)
        factory = self._new_group('Factory Expense', self.type_expense)
        self.assertEqual(office.code_prefix_start, '06001')
        self.assertEqual(factory.code_prefix_start, '06002')

        supplies = self.env['account.account'].create({
            'name': 'Office supplies expense',
            'account_type': 'expense',
            'coding_group_id': office.id,
        })
        marketing = self.env['account.account'].create({
            'name': 'Office marketing expense',
            'account_type': 'expense',
            'coding_group_id': office.id,
        })
        self.assertEqual(supplies.code, '06001001')
        self.assertEqual(marketing.code, '06001002')
        self.assertEqual(supplies.group_id, office)
