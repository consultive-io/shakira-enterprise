from odoo.tests import tagged

from .common import LastBalanceCommon


@tagged('post_install', '-at_install')
class TestJournalEntryLastBalance(LastBalanceCommon):
    """Journal entry lines show the Due of their own partner.

    A journal entry has no header partner worth reading, so ``account.move``
    leaves its Last Balance at zero for one. The figure belongs on the line,
    where the partner actually is.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Both sides open on partner_a, so its Due is a net figure.
        cls.init_invoice('out_invoice', partner=cls.partner_a, amounts=[1000.0], post=True)
        cls.init_invoice('in_invoice', partner=cls.partner_a, amounts=[300.0], post=True)
        cls.init_invoice('out_invoice', partner=cls.partner_b, amounts=[500.0], post=True)
        cls.john = cls.env['res.partner'].create({
            'name': "John Doe", 'parent_id': cls.partner_a.id,
        })

    def _due(self, partner, company):
        return partner.with_company(company).total_all_due

    def _entry(self, partners):
        """A journal entry with one balanced pair of lines per partner."""
        account = self.company_data['default_account_revenue']
        lines = []
        for index, partner in enumerate(partners, start=1):
            lines += [
                (0, 0, {'account_id': account.id, 'partner_id': partner.id,
                        'debit': 100.0 * index, 'credit': 0.0}),
                (0, 0, {'account_id': account.id, 'partner_id': partner.id,
                        'debit': 0.0, 'credit': 100.0 * index}),
            ]
        return self.env['account.move'].create({'move_type': 'entry', 'line_ids': lines})

    def test_a_line_shows_its_own_partners_due(self):
        entry = self._entry([self.partner_a])
        due = self._due(self.partner_a, entry.company_id)

        self.assertTrue(due)
        for line in entry.line_ids:
            self.assertAlmostEqual(line.partner_last_balance, due)

    def test_each_line_reads_its_own_partner(self):
        """The point of a line-level field: one entry, several partners."""
        entry = self._entry([self.partner_a, self.partner_b])
        due_a = self._due(self.partner_a, entry.company_id)
        due_b = self._due(self.partner_b, entry.company_id)

        self.assertNotAlmostEqual(due_a, due_b)
        for line in entry.line_ids:
            expected = due_a if line.partner_id == self.partner_a else due_b
            self.assertAlmostEqual(line.partner_last_balance, expected)

    def test_a_line_without_a_partner_reads_zero(self):
        account = self.company_data['default_account_revenue']
        entry = self.env['account.move'].create({
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {'account_id': account.id, 'debit': 100.0, 'credit': 0.0}),
                (0, 0, {'account_id': account.id, 'debit': 0.0, 'credit': 100.0}),
            ],
        })
        for line in entry.line_ids:
            self.assertFalse(line.partner_id)
            self.assertEqual(line.partner_last_balance, 0.0)

    def test_a_contact_person_line_shows_their_companys_due(self):
        """Lines are booked on the commercial entity, so the person reads its Due."""
        entry = self._entry([self.john])
        due = self._due(self.partner_a, entry.company_id)

        self.assertTrue(due)
        for line in entry.line_ids:
            self.assertAlmostEqual(line.partner_last_balance, due)

    def test_the_line_figure_matches_the_header_field_on_an_invoice(self):
        """One balance per partner, whether read from the header or from a line."""
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[50.0])
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_type == 'asset_receivable')

        self.assertTrue(receivable)
        self.assertAlmostEqual(
            receivable[0].partner_last_balance, invoice.partner_last_balance)

    def test_the_header_still_reads_zero_on_an_entry(self):
        """The line field fills the gap; it does not change the header."""
        entry = self._entry([self.partner_a])
        self.assertEqual(entry.partner_last_balance, 0.0)
        self.assertTrue(entry.line_ids[0].partner_last_balance)

    def test_repeated_partners_are_read_once(self):
        """Twenty lines on one partner must not mean twenty readings.

        total_all_due is computed, not stored, and is read through with_company,
        so a naive per-line compute would recompute it for every line.
        """
        entry = self._entry([self.partner_a] * 10)
        self.assertEqual(len(entry.line_ids), 20)

        Partner = type(self.env['res.partner'])
        original = Partner._get_last_balance
        readings = []

        def counting(partner, company):
            readings.append(partner.id)
            return original(partner, company)

        self.patch(Partner, '_get_last_balance', counting)
        entry.line_ids.invalidate_recordset(['partner_last_balance'])
        values = entry.line_ids.mapped('partner_last_balance')

        self.assertEqual(len(readings), 1, "one reading covers all 20 lines")
        due = self._due(self.partner_a, entry.company_id)
        self.assertTrue(due)
        for value in values:
            self.assertAlmostEqual(value, due)
