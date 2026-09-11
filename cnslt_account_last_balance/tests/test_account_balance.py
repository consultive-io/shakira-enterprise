from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountBalanceColumn(TransactionCase):
    """The Chart of Accounts list shows the figure on the account's Balance button."""

    def _arch(self, xmlid, view_type):
        return self.env['account.account'].get_view(self.env.ref(xmlid).id, view_type)['arch']

    def test_the_list_shows_the_balance_as_money(self):
        arch = self._arch('account.view_account_list', 'list')

        self.assertRegex(arch, r'<field name="current_balance"[^>]*widget="monetary"')
        # the currency the monetary widget formats with has to be in the list too
        self.assertIn('name="company_currency_id"', arch)

    def test_it_is_the_field_behind_the_forms_balance_button(self):
        form = self._arch('account.view_account_form', 'form')

        self.assertRegex(form, r'o_stat_value">\s*<field name="current_balance"')
