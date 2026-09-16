from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBankBranch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Branch = cls.env['res.bank.branch']
        cls.motijheel = Branch.create({'name': "Motijheel", 'route': '090274560'})
        cls.gulshan = Branch.create({'name': "Gulshan", 'route': '090261725'})
        cls.dhanmondi = Branch.create({'name': "Dhanmondi", 'route': '060261098'})
        cls.bank_a = cls.env['res.bank'].create({
            'name': "Bank A", 'branch_ids': [(6, 0, (cls.motijheel | cls.gulshan).ids)],
        })
        cls.bank_b = cls.env['res.bank'].create({
            'name': "Bank B", 'branch_ids': [(6, 0, cls.dhanmondi.ids)],
        })
        cls.partner = cls.env['res.partner'].create({'name': "Account Holder"})

    def _account(self, **values):
        return self.env['res.partner.bank'].create({
            'acc_number': values.pop('acc_number', '0001'),
            'partner_id': self.partner.id,
            **values,
        })

    def test_account_is_offered_its_banks_branches(self):
        account = self._account(bank_id=self.bank_a.id)
        self.assertEqual(account.allowed_branch_ids, self.motijheel | self.gulshan)

    def test_account_takes_a_branch_of_its_bank(self):
        account = self._account(bank_id=self.bank_a.id, branch_id=self.gulshan.id)
        self.assertEqual(account.branch_id, self.gulshan)

    def test_account_shows_its_branchs_routing_number(self):
        account = self._account(bank_id=self.bank_a.id, branch_id=self.gulshan.id)
        self.assertEqual(account.branch_route, '090261725')

    def test_the_routing_number_follows_the_branch(self):
        """Related and unstored, so correcting the branch corrects the account."""
        account = self._account(bank_id=self.bank_a.id, branch_id=self.gulshan.id)
        self.gulshan.route = '090261726'
        self.assertEqual(account.branch_route, '090261726')

    def test_no_branch_means_no_routing_number(self):
        account = self._account(bank_id=self.bank_a.id)
        self.assertFalse(account.branch_route)

    def test_branch_of_another_bank_is_refused(self):
        """The domain is client-side, so the ORM path has to refuse it too."""
        with self.assertRaises(ValidationError):
            self._account(bank_id=self.bank_a.id, branch_id=self.dhanmondi.id)

    def test_branch_without_a_bank_is_refused(self):
        with self.assertRaises(ValidationError):
            self._account(branch_id=self.motijheel.id)

    def test_a_branch_listed_on_two_banks_works_for_both(self):
        self.bank_b.branch_ids = [(4, self.motijheel.id)]
        for bank in (self.bank_a, self.bank_b):
            account = self._account(
                acc_number='SHARED-%s' % bank.id, bank_id=bank.id, branch_id=self.motijheel.id,
            )
            self.assertEqual(account.branch_id, self.motijheel)

    def test_changing_the_bank_clears_a_branch_it_does_not_list(self):
        with Form(self.env['res.partner.bank']) as form:
            form.acc_number = '0002'
            form.partner_id = self.partner
            form.bank_id = self.bank_a
            form.branch_id = self.gulshan
            form.bank_id = self.bank_b
            self.assertFalse(form.branch_id)

    def test_changing_to_a_bank_that_lists_the_branch_keeps_it(self):
        self.bank_b.branch_ids = [(4, self.gulshan.id)]
        with Form(self.env['res.partner.bank']) as form:
            form.acc_number = '0003'
            form.partner_id = self.partner
            form.bank_id = self.bank_a
            form.branch_id = self.gulshan
            form.bank_id = self.bank_b
            self.assertEqual(form.branch_id, self.gulshan)
