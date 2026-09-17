import re

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAssignSerials(TransactionCase):
    """One click on a receipt numbers every serial-tracked unit on it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'XF',
        })
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'XH',
        })
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'XI',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'XT', 'parent_id': cls.induction.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1,
        )
        cls.stock = cls.warehouse.lot_stock_id
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')

    def setUp(self):
        super().setUp()
        # Per test, not per class: the counters are PostgreSQL sequences, whose
        # draws survive the rollback between tests. A product made here gets a
        # counter that is born and discarded with the test.
        self.cooker = self._make_product("Cooker")
        self.hob = self._make_product("Hob")
        self.bracket = self._make_product("Bracket", tracking='none')
        self.powder = self._make_product("Powder", tracking='lot')

    def _make_product(self, name, tracking='serial'):
        return self.env['product.template'].create({
            'name': name,
            'is_storable': True,
            'tracking': tracking,
            'inventory_category_id': self.finished_goods.id,
            'inventory_type_id': self.home_appliance.id,
            'categ_id': self.flat_top.id,
        })

    def _picking(self, picking_type, source, destination, lines):
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
        })
        for product, quantity in lines:
            self.env['stock.move'].create({
                'product_id': product.product_variant_id.id,
                'product_uom_qty': quantity,
                'picking_id': picking.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _receipt(self, lines):
        return self._picking(self.warehouse.in_type_id, self.supplier_location, self.stock, lines)

    def _serials(self, picking, product):
        lines = picking.move_line_ids.filtered(lambda line: line.product_id == product.product_variant_id)
        return sorted(name for name in lines.mapped('lot_name') if name)

    def _expected(self, product, *numbers):
        return ['%s%06d' % (product.default_code, number) for number in numbers]

    # -- the click ------------------------------------------------------------------

    def test_one_click_numbers_every_serial_product_to_its_demand(self):
        receipt = self._receipt([(self.cooker, 3), (self.hob, 2), (self.bracket, 5), (self.powder, 4)])

        receipt.action_assign_serial_numbers()

        self.assertEqual(self._serials(receipt, self.cooker), self._expected(self.cooker, 1, 2, 3))
        self.assertEqual(self._serials(receipt, self.hob), self._expected(self.hob, 1, 2))
        cooker_lines = receipt.move_line_ids.filtered(
            lambda line: line.product_id == self.cooker.product_variant_id,
        )
        self.assertEqual(cooker_lines.mapped('quantity'), [1.0, 1.0, 1.0])

    def test_lot_tracked_and_untracked_products_are_left_alone(self):
        receipt = self._receipt([(self.cooker, 1), (self.bracket, 5), (self.powder, 4)])

        receipt.action_assign_serial_numbers()

        self.assertFalse(self._serials(receipt, self.bracket))
        self.assertFalse(self._serials(receipt, self.powder))
        self.assertEqual(receipt.move_ids.filtered(
            lambda move: move.product_id == self.powder.product_variant_id,
        ).quantity, 4.0)

    # -- the counter ---------------------------------------------------------------

    def test_the_counter_moves_past_every_serial_issued(self):
        """Core's server-side generator leaves the counter where it was; the
        next receipt would then be handed numbers already in use."""
        self._receipt([(self.cooker, 3)]).action_assign_serial_numbers()
        second = self._receipt([(self.cooker, 2)])

        second.action_assign_serial_numbers()

        self.assertEqual(self._serials(second, self.cooker), self._expected(self.cooker, 4, 5))

    def test_clicking_again_issues_nothing_more(self):
        receipt = self._receipt([(self.cooker, 3)])
        receipt.action_assign_serial_numbers()
        serials = self._serials(receipt, self.cooker)
        counter = self.cooker.lot_sequence_id.number_next_actual

        receipt.action_assign_serial_numbers()

        self.assertEqual(self._serials(receipt, self.cooker), serials)
        self.assertEqual(self.cooker.lot_sequence_id.number_next_actual, counter)

    def test_a_partly_numbered_line_is_topped_up(self):
        receipt = self._receipt([(self.cooker, 3)])
        receipt.move_line_ids[:1].write({'lot_name': 'HAND-0001', 'quantity': 1})

        receipt.action_assign_serial_numbers()

        self.assertEqual(
            self._serials(receipt, self.cooker),
            sorted(['HAND-0001', *self._expected(self.cooker, 1, 2)]),
        )

    def test_a_counter_behind_issued_serials_is_refused(self):
        self.env['stock.lot'].create({
            'name': self._expected(self.cooker, 1)[0],
            'product_id': self.cooker.product_variant_id.id,
        })
        receipt = self._receipt([(self.cooker, 1)])

        with self.assertRaisesRegex(UserError, "Resync Counter"):
            receipt.action_assign_serial_numbers()

    # -- afterwards ------------------------------------------------------------------

    def test_validating_receives_the_assigned_serials(self):
        receipt = self._receipt([(self.cooker, 2)])
        receipt.action_assign_serial_numbers()

        receipt.button_validate()

        self.assertEqual(receipt.state, 'done')
        lots = self.env['stock.lot'].search([('product_id', '=', self.cooker.product_variant_id.id)])
        self.assertEqual(sorted(lots.mapped('name')), self._expected(self.cooker, 1, 2))
        # the receipt's batch hook still runs on top
        self.assertEqual(receipt.serial_batch_ids.lot_ids, lots)

    # -- the button ------------------------------------------------------------------

    def test_the_button_shows_only_while_serials_are_missing(self):
        receipt = self._receipt([(self.cooker, 2)])
        self.assertTrue(receipt.show_assign_serials)

        receipt.action_assign_serial_numbers()

        self.assertFalse(receipt.show_assign_serials)

    def test_receipts_with_nothing_to_number_do_not_show_it(self):
        receipt = self._receipt([(self.bracket, 5), (self.powder, 4)])

        self.assertFalse(receipt.show_assign_serials)

    def test_deliveries_do_not_show_it(self):
        delivery = self._picking(
            self.warehouse.out_type_id, self.stock, self.customer_location, [(self.cooker, 1)],
        )

        self.assertFalse(delivery.show_assign_serials)

    def test_the_button_sits_before_validate(self):
        arch = self.env['stock.picking'].get_view(
            self.env.ref('stock.view_picking_form').id, 'form',
        )['arch']

        self.assertRegex(
            arch, re.compile(r'name="action_assign_serial_numbers".*?name="button_validate"', re.S),
        )
