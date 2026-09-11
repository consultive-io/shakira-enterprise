from odoo.tests import Form, new_test_user, tagged

from .common import LastBalanceCommon


@tagged('post_install', '-at_install')
class TestLastBalance(LastBalanceCommon):
    """Invoices, bills, credit notes and payments show the contact's Due.

    Every expectation is read from total_all_due -- the field behind the Due
    button -- rather than from a hand-summed figure, because matching that
    button is the whole requirement.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Both sides open on the same partner, so the Due is a net figure.
        cls.init_invoice('out_invoice', partner=cls.partner_a, amounts=[1000.0], post=True)
        cls.init_invoice('in_invoice', partner=cls.partner_a, amounts=[300.0], post=True)
        cls.john = cls.env['res.partner'].create({
            'name': "John Doe", 'parent_id': cls.partner_a.id,
        })

    def _due(self, partner, company):
        return partner.with_company(company).total_all_due

    # -- invoices, bills, credit notes ------------------------------------------

    def test_an_invoice_shows_the_contacts_due(self):
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[50.0])
        due = self._due(self.partner_a, invoice.company_id)

        self.assertTrue(due)
        self.assertAlmostEqual(invoice.partner_last_balance, due)

    def test_the_due_is_net_of_what_you_owe_them(self):
        """Receivable less payable, as the button shows -- not receivable alone."""
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[50.0])
        receivable = self.partner_a.with_company(invoice.company_id).credit

        self.assertLess(invoice.partner_last_balance, receivable)

    def test_bills_and_credit_notes_show_the_same_figure(self):
        """One balance per partner, whichever side the document is on."""
        documents = (
            self.init_invoice('in_invoice', partner=self.partner_a, amounts=[50.0])
            | self.init_invoice('out_refund', partner=self.partner_a, amounts=[50.0])
            | self.init_invoice('in_refund', partner=self.partner_a, amounts=[50.0])
        )
        due = self._due(self.partner_a, documents[0].company_id)

        for document in documents:
            with self.subTest(move_type=document.move_type):
                self.assertAlmostEqual(document.partner_last_balance, due)

    def test_a_contact_person_shows_their_companys_due(self):
        """Lines are booked on the company, so the person alone would read 0."""
        invoice = self.init_invoice('out_invoice', partner=self.john, amounts=[50.0])

        self.assertFalse(self._due(self.john, invoice.company_id))
        self.assertAlmostEqual(
            invoice.partner_last_balance, self._due(self.partner_a, invoice.company_id),
        )

    def test_a_journal_entry_shows_nothing(self):
        entry = self.env['account.move'].create({
            'move_type': 'entry', 'partner_id': self.partner_a.id,
        })

        self.assertEqual(entry.partner_last_balance, 0.0)

    def test_it_follows_the_partner_as_it_is_chosen(self):
        form = Form(self.env['account.move'].with_context(default_move_type='out_invoice'))

        form.partner_id = self.partner_a
        self.assertAlmostEqual(
            form.partner_last_balance, self._due(self.partner_a, self.env.company),
        )

        form.partner_id = self.partner_b
        self.assertEqual(form.partner_last_balance, 0.0)

    # -- payments --------------------------------------------------------------

    def test_a_payment_shows_the_contacts_due(self):
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_a.id,
            'amount': 100.0,
            'journal_id': self.company_data['default_journal_bank'].id,
        })

        self.assertAlmostEqual(
            payment.partner_last_balance, self._due(self.partner_a, payment.company_id),
        )

    # -- who sees it -------------------------------------------------------------

    def test_only_people_who_can_see_the_due_see_the_balance(self):
        """Same groups as the Due itself: an order must not leak what the
        contact would hide."""
        employee = new_test_user(self.env, login='lb_employee', groups='base.group_user')
        billing = new_test_user(
            self.env, login='lb_billing',
            groups='base.group_user,account.group_account_invoice',
        )

        for model in ('account.move', 'account.payment'):
            with self.subTest(model=model):
                self.assertNotIn(
                    'partner_last_balance',
                    self.env[model].with_user(employee).fields_get(['partner_last_balance']),
                )
                self.assertIn(
                    'partner_last_balance',
                    self.env[model].with_user(billing).fields_get(['partner_last_balance']),
                )
