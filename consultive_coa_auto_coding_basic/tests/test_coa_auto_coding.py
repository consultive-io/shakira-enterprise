from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestCoaAutoCoding(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root_company = cls.env.company.root_id
        cls.root_company.caac_serial_width = 3

        Group = cls.env['account.group']
        cls.group_assets = Group.create({
            'name': 'Assets',
            'code_prefix_start': '1',
            'code_prefix_end': '1',
            'company_id': cls.root_company.id,
        })
        cls.group_cash = Group.create({
            'name': 'Cash',
            'code_prefix_start': '10101',
            'code_prefix_end': '10101',
            'company_id': cls.root_company.id,
        })
        cls.group_bank = Group.create({
            'name': 'Bank',
            'code_prefix_start': '10102',
            'code_prefix_end': '10102',
            'company_id': cls.root_company.id,
        })

    def _new_account(self, group, **kwargs):
        values = {
            'name': 'Test Account',
            'account_type': 'asset_cash',
            'coding_group_id': group.id,
        }
        values.update(kwargs)
        return self.env['account.account'].create(values)

    # -- defaults ------------------------------------------------------

    def test_coding_prefix_defaults_to_start_prefix(self):
        self.assertEqual(self.group_bank.coding_prefix, '10102')

    def test_effective_width_falls_back_to_company(self):
        self.assertEqual(self.group_bank._caac_effective_width(self.root_company), 3)
        self.group_bank.coding_serial_width = 4
        self.assertEqual(self.group_bank._caac_effective_width(self.root_company), 4)

    # -- generation ----------------------------------------------------

    def test_first_code_starts_at_one(self):
        account = self._new_account(self.group_bank)
        self.assertEqual(account.code, '10102001')

    def test_serial_increments_within_group(self):
        first = self._new_account(self.group_bank)
        second = self._new_account(self.group_bank)
        self.assertEqual(first.code, '10102001')
        self.assertEqual(second.code, '10102002')

    def test_groups_have_independent_serials(self):
        bank = self._new_account(self.group_bank)
        cash = self._new_account(self.group_cash)
        self.assertEqual(bank.code, '10102001')
        self.assertEqual(cash.code, '10101001')

    def test_batch_creation_does_not_collide(self):
        accounts = self.env['account.account'].create([
            {'name': f'Batch {index}', 'account_type': 'asset_cash',
             'coding_group_id': self.group_bank.id}
            for index in range(5)
        ])
        self.assertEqual(
            accounts.mapped('code'),
            ['10102001', '10102002', '10102003', '10102004', '10102005'],
        )

    def test_gaps_are_not_reused(self):
        first = self._new_account(self.group_bank)
        second = self._new_account(self.group_bank)
        first.unlink()
        third = self._new_account(self.group_bank)
        self.assertEqual(second.code, '10102002')
        self.assertEqual(third.code, '10102003')

    def test_manually_created_code_is_respected(self):
        self.env['account.account'].create({
            'name': 'Manual',
            'account_type': 'asset_cash',
            'code': '10102007',
            'coding_mode': 'manual',
        })
        generated = self._new_account(self.group_bank)
        self.assertEqual(generated.code, '10102008')

    def test_custom_serial_width(self):
        self.group_bank.coding_serial_width = 2
        account = self._new_account(self.group_bank)
        self.assertEqual(account.code, '1010201')

    def test_custom_coding_prefix_overrides_range_start(self):
        group = self.env['account.group'].create({
            'name': 'Range',
            'code_prefix_start': '20100',
            'code_prefix_end': '20199',
            'company_id': self.root_company.id,
            'coding_prefix': '20150',
        })
        account = self._new_account(group, account_type='liability_current')
        self.assertEqual(account.code, '20150001')

    # -- guard rails ---------------------------------------------------

    def test_manual_mode_skips_generation(self):
        account = self.env['account.account'].create({
            'name': 'Manual',
            'account_type': 'asset_cash',
            'code': '99999',
            'coding_mode': 'manual',
            'coding_group_id': self.group_bank.id,
        })
        self.assertEqual(account.code, '99999')

    def test_serial_exhaustion_raises(self):
        self.group_bank.coding_serial_width = 1
        for _index in range(9):
            self._new_account(self.group_bank)
        with self.assertRaises(ValidationError):
            self._new_account(self.group_bank)

    def test_child_group_capture_is_blocked(self):
        # A child group whose prefix range swallows part of the parent's serials.
        self.env['account.group'].create({
            'name': 'Capturing child',
            'code_prefix_start': '101020',
            'code_prefix_end': '101020',
            'company_id': self.root_company.id,
        })
        with self.assertRaises(ValidationError):
            self._new_account(self.group_bank)

    def test_invalid_prefix_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.group_bank.coding_prefix = '101-02'

    def test_generated_code_resolves_back_to_group(self):
        account = self._new_account(self.group_bank)
        self.assertEqual(account.group_id, self.group_bank)

    # -- regeneration --------------------------------------------------

    def test_regenerate_is_idempotent_for_single_account(self):
        # Regression: the account's own code was counted as taken, so every click
        # walked it forward (10102001 -> 10102002 -> 10102003 ...).
        account = self._new_account(self.group_bank)
        self.assertEqual(account.code, '10102001')
        account.action_caac_regenerate_code()
        self.assertEqual(account.code, '10102001')
        account.action_caac_regenerate_code()
        self.assertEqual(account.code, '10102001')

    def test_regenerate_is_idempotent_for_last_account(self):
        self._new_account(self.group_bank)
        last = self._new_account(self.group_bank)
        self.assertEqual(last.code, '10102002')
        last.action_caac_regenerate_code()
        self.assertEqual(last.code, '10102002')

    def test_regenerate_moves_mid_sequence_account_to_the_end(self):
        first = self._new_account(self.group_bank)
        middle = self._new_account(self.group_bank)
        last = self._new_account(self.group_bank)
        middle.action_caac_regenerate_code()
        self.assertEqual(first.code, '10102001')
        self.assertEqual(last.code, '10102003')
        self.assertEqual(middle.code, '10102004')

    def test_regenerate_after_group_change(self):
        account = self._new_account(self.group_bank)
        account.coding_group_id = self.group_cash
        account.action_caac_regenerate_code()
        self.assertEqual(account.code, '10101001')

    def test_regenerate_does_not_free_the_serial_for_others(self):
        account = self._new_account(self.group_bank)
        account.action_caac_regenerate_code()
        other = self._new_account(self.group_bank)
        self.assertEqual(other.code, '10102002')

    def test_regenerate_refused_for_manual_account(self):
        account = self.env['account.account'].create({
            'name': 'Manual',
            'account_type': 'asset_cash',
            'code': '10102900',
            'coding_mode': 'manual',
        })
        with self.assertRaises(UserError):
            account.action_caac_regenerate_code()

    # -- previews ------------------------------------------------------

    def test_preview_matches_next_allocation(self):
        self._new_account(self.group_bank)
        preview = self.env['account.account']._caac_peek_code(
            self.group_bank, self.root_company,
        )
        self.assertEqual(preview, '10102002')
        self.assertEqual(self._new_account(self.group_bank).code, preview)

    def test_preview_on_saved_account_excludes_itself(self):
        account = self._new_account(self.group_bank)
        account.invalidate_recordset(['coding_next_code'])
        self.assertEqual(account.coding_next_code, account.code)

    def test_group_next_code_field(self):
        self._new_account(self.group_bank)
        self.group_bank.invalidate_recordset(['coding_next_code'])
        self.assertEqual(self.group_bank.coding_next_code, '10102002')

    # -- escape hatch --------------------------------------------------

    def test_context_flag_disables_generation(self):
        account = self.env['account.account'].with_context(caac_no_autocode=True).create({
            'name': 'Imported',
            'account_type': 'asset_cash',
            'code': '10102500',
            'coding_group_id': self.group_bank.id,
        })
        self.assertEqual(account.code, '10102500')
