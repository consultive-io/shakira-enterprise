import re

from odoo.tests import Form, new_test_user, tagged

from .common import LastBalanceCommon


@tagged('post_install', '-at_install')
class TestSaleLastBalance(LastBalanceCommon):

    @classmethod
    def get_default_groups(cls):
        # The accounting fixture's user gets Purchase, Stock and MRP rights but
        # not Sales, so it could not create the orders these tests are about.
        return super().get_default_groups() | cls.env.ref('sales_team.group_sale_salesman')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.init_invoice('out_invoice', partner=cls.partner_a, amounts=[1000.0], post=True)
        cls.john = cls.env['res.partner'].create({
            'name': "John Doe", 'parent_id': cls.partner_a.id,
        })

    def _due(self, partner, company):
        return partner.with_company(company).total_all_due

    def test_a_sales_order_shows_the_contacts_due(self):
        order = self.env['sale.order'].create({'partner_id': self.partner_a.id})
        due = self._due(self.partner_a, order.company_id)

        self.assertTrue(due)
        self.assertAlmostEqual(order.partner_last_balance, due)

    def test_ordering_for_a_contact_person_shows_their_companys_due(self):
        order = self.env['sale.order'].create({'partner_id': self.john.id})

        self.assertAlmostEqual(
            order.partner_last_balance, self._due(self.partner_a, order.company_id),
        )

    def test_it_follows_the_customer_as_it_is_chosen(self):
        form = Form(self.env['sale.order'])

        form.partner_id = self.partner_a
        self.assertAlmostEqual(
            form.partner_last_balance, self._due(self.partner_a, self.env.company),
        )

        form.partner_id = self.partner_b
        self.assertEqual(form.partner_last_balance, 0.0)

    def test_a_salesperson_without_invoicing_rights_does_not_see_it(self):
        seller = new_test_user(self.env, login='lb_seller', groups='sales_team.group_sale_salesman')

        self.assertNotIn(
            'partner_last_balance',
            self.env['sale.order'].with_user(seller).fields_get(['partner_last_balance']),
        )

    def test_the_balance_sits_under_the_customer(self):
        arch = self.env['sale.order'].get_view(self.env.ref('sale.view_order_form').id, 'form')['arch']

        self.assertRegex(
            arch, re.compile(r'name="partner_id".*?name="partner_last_balance"', re.S),
        )
