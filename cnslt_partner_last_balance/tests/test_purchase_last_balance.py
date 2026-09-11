import re

from odoo.tests import Form, new_test_user, tagged

from .common import LastBalanceCommon


@tagged('post_install', '-at_install')
class TestPurchaseLastBalance(LastBalanceCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A bill alone: what you owe the vendor, so the Due is negative.
        cls.init_invoice('in_invoice', partner=cls.partner_a, amounts=[1000.0], post=True)
        cls.john = cls.env['res.partner'].create({
            'name': "John Doe", 'parent_id': cls.partner_a.id,
        })

    def _due(self, partner, company):
        return partner.with_company(company).total_all_due

    def test_a_purchase_order_shows_the_contacts_due(self):
        order = self.env['purchase.order'].create({'partner_id': self.partner_a.id})
        due = self._due(self.partner_a, order.company_id)

        self.assertLess(due, 0.0)
        self.assertAlmostEqual(order.partner_last_balance, due)

    def test_ordering_from_a_contact_person_shows_their_companys_due(self):
        order = self.env['purchase.order'].create({'partner_id': self.john.id})

        self.assertAlmostEqual(
            order.partner_last_balance, self._due(self.partner_a, order.company_id),
        )

    def test_it_follows_the_vendor_as_it_is_chosen(self):
        form = Form(self.env['purchase.order'])

        form.partner_id = self.partner_a
        self.assertAlmostEqual(
            form.partner_last_balance, self._due(self.partner_a, self.env.company),
        )

        form.partner_id = self.partner_b
        self.assertEqual(form.partner_last_balance, 0.0)

    def test_a_buyer_without_invoicing_rights_does_not_see_it(self):
        buyer = new_test_user(self.env, login='lb_buyer', groups='purchase.group_purchase_user')

        self.assertNotIn(
            'partner_last_balance',
            self.env['purchase.order'].with_user(buyer).fields_get(['partner_last_balance']),
        )

    def test_the_balance_sits_under_the_vendor(self):
        arch = self.env['purchase.order'].get_view(
            self.env.ref('purchase.purchase_order_form').id, 'form',
        )['arch']

        self.assertRegex(
            arch, re.compile(r'name="partner_id".*?name="partner_last_balance"', re.S),
        )
