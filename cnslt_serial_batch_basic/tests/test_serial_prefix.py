from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSerialPrefix(TransactionCase):
    """The prefix and the padding, which together decide the serial number shape.

    Everything here leans on Odoo's own per-product sequence rather than on a
    generator of our own, so several of these tests are really pinning core
    behaviour we depend on and would want to hear about if it changed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'ZF',
        })
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'ZH',
        })
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'ZI',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'ZT', 'parent_id': cls.induction.id,
        })

    def _make_product(self, name="Cooker", **extra):
        values = {
            'name': name,
            'is_storable': True,
            'inventory_category_id': self.finished_goods.id,
            'inventory_type_id': self.home_appliance.id,
            'categ_id': self.flat_top.id,
        }
        values.update(extra)
        return self.env['product.template'].create(values)

    # -- assignment ---------------------------------------------------------

    def test_prefix_is_the_internal_reference(self):
        product = self._make_product()
        self.assertEqual(product.default_code, 'ZIZT001')
        self.assertEqual(product.serial_prefix_format, 'ZIZT001')

    def test_sequence_is_created_with_our_padding(self):
        """Odoo hardcodes padding 7; 7 + a 7-character prefix would be 14 characters."""
        product = self._make_product()
        sequence = product.lot_sequence_id

        self.assertTrue(sequence)
        self.assertEqual(sequence.padding, 6)
        self.assertEqual(sequence.prefix, 'ZIZT001')
        self.assertEqual(sequence.number_increment, 1)

    def test_first_serial_is_thirteen_characters(self):
        """The whole point of the padding override."""
        product = self._make_product()
        serial = product.lot_sequence_id.next_by_id()

        self.assertEqual(serial, 'ZIZT001000001')
        self.assertEqual(len(serial), 13)

    def test_serial_continues_rather_than_restarting(self):
        product = self._make_product()
        issued = [product.lot_sequence_id.next_by_id() for _ in range(3)]

        self.assertEqual(issued, ['ZIZT001000001', 'ZIZT001000002', 'ZIZT001000003'])

    def test_two_products_do_not_share_a_counter(self):
        """Odoo reuses a sequence when the prefix matches, so distinct Internal
        References are what keep the counters apart."""
        first = self._make_product("Cooker")
        second = self._make_product("Griddle")

        self.assertNotEqual(first.default_code, second.default_code)
        self.assertNotEqual(first.lot_sequence_id, second.lot_sequence_id)
        self.assertEqual(first.lot_sequence_id.next_by_id(), 'ZIZT001000001')
        self.assertEqual(second.lot_sequence_id.next_by_id(), 'ZIZT002000001')

    def test_sequence_is_not_the_shared_default(self):
        """A product left on stock.sequence_production_lots would issue unprefixed
        serials shared with every other product."""
        product = self._make_product()
        shared = self.env.ref('stock.sequence_production_lots')

        self.assertNotEqual(product.lot_sequence_id, shared)

    def test_coded_storable_goods_are_tracked_by_serial(self):
        product = self._make_product()
        self.assertEqual(product.tracking, 'serial')

    def test_non_storable_goods_are_left_untracked(self):
        """_compute_tracking forces 'none' back onto anything not storable, so
        setting it would be silently undone rather than honoured."""
        product = self._make_product("Consumable", is_storable=False)
        self.assertEqual(product.tracking, 'none')

    def test_services_get_no_prefix(self):
        service = self.env['product.template'].create({
            'name': "Installation", 'type': 'service',
        })
        self.assertFalse(service.item_code)
        self.assertFalse(service.serial_prefix_format)

    # -- ordering -----------------------------------------------------------

    def test_prefix_uses_the_freshly_written_code(self):
        """The inverse runs on flush, after the code is written. Pins that it reads
        the new Internal Reference and not a stale one."""
        product = self._make_product()
        self.env.flush_all()

        self.assertEqual(product.lot_sequence_id.prefix, product.default_code)

    def test_regenerating_the_code_moves_the_prefix_with_it(self):
        product = self._make_product()
        self.assertEqual(product.serial_prefix_format, 'ZIZT001')

        product.action_regenerate_item_code()

        self.assertEqual(product.default_code, 'ZIZT002')
        self.assertEqual(product.serial_prefix_format, 'ZIZT002')
        self.assertEqual(product.lot_sequence_id.padding, 6)
        self.assertEqual(product.lot_sequence_id.next_by_id(), 'ZIZT002000001')

    # -- not ours to touch --------------------------------------------------

    def test_a_hand_configured_sequence_is_left_alone(self):
        """Odoo reuses any sequence whose prefix matches, so a product can end up
        pointing at one an administrator built. Rewriting its padding would change
        how somebody else's stock is numbered."""
        manual = self.env['ir.sequence'].create({
            'name': "Hand Built",
            'code': 'x_manual_serial',
            'prefix': 'MANUAL',
            'padding': 4,
            'company_id': False,
        })
        product = self._make_product()
        product.lot_sequence_id = manual
        product._align_serial_sequence()

        self.assertEqual(manual.padding, 4, "a sequence we did not create must not be rewritten")

    def test_the_shared_default_sequence_is_never_claimed(self):
        """The worst case the guard exists for.

        A product with no code sits on Odoo's global lot sequence, and that
        sequence's prefix is empty as well. Comparing empty against empty would
        claim it, and rewriting its padding would change lot numbering for every
        product in the database that has no prefix of its own.
        """
        shared = self.env.ref('stock.sequence_production_lots')
        original_padding = shared.padding
        service = self.env['product.template'].create({
            'name': "Installation", 'type': 'service',
        })

        self.assertFalse(service._serial_prefix())
        self.assertFalse(service._serial_sequence_is_ours(shared))

        service.serial_prefix_format = False
        self.env.flush_all()
        shared.invalidate_recordset()

        self.assertEqual(
            shared.padding, original_padding,
            "Odoo's shared lot sequence must never be rewritten",
        )

    def test_a_sequence_for_a_different_prefix_is_left_alone(self):
        """Right code, wrong product: still not ours."""
        other = self.env['ir.sequence'].create({
            'name': "Other Product Serial",
            'code': 'stock.lot.serial',
            'prefix': 'SOMEONE',
            'padding': 7,
            'company_id': False,
        })
        product = self._make_product()
        product.lot_sequence_id = other
        product._align_serial_sequence()

        self.assertEqual(other.padding, 7)

    # -- backfill -----------------------------------------------------------

    def test_backfill_populates_products_missing_a_prefix(self):
        product = self._make_product()
        product.serial_prefix_format = False
        self.assertFalse(product.serial_prefix_format)

        self.assertEqual(product.action_backfill_serial_prefix(), 1)

        self.assertEqual(product.serial_prefix_format, 'ZIZT001')
        self.assertEqual(product.lot_sequence_id.padding, 6)

    def test_backfill_keeps_the_internal_reference(self):
        """Backfilling must not draw a new number: the old code may already be
        printed on labels and purchase orders."""
        product = self._make_product()
        product.serial_prefix_format = False

        product.action_backfill_serial_prefix()

        self.assertEqual(product.default_code, 'ZIZT001')
        self.assertEqual(product.item_code, 'ZFZHZIZT001')

    def test_backfill_is_safe_to_repeat(self):
        product = self._make_product()
        product.serial_prefix_format = False
        product.action_backfill_serial_prefix()
        sequence = product.lot_sequence_id

        self.assertFalse(product.action_backfill_serial_prefix())
        self.assertEqual(product.lot_sequence_id, sequence)

    def test_backfill_leaves_an_already_prefixed_product_alone(self):
        product = self._make_product()
        sequence = product.lot_sequence_id

        self.assertFalse(product.action_backfill_serial_prefix())
        self.assertEqual(product.lot_sequence_id, sequence)

    def test_backfill_sweeps_the_catalogue_when_called_on_nothing(self):
        """The one-off deployment path: no selection, so it finds them itself."""
        first = self._make_product("Cooker")
        second = self._make_product("Griddle")
        (first + second).write({'serial_prefix_format': False})

        swept = self.env['product.template'].action_backfill_serial_prefix()

        self.assertGreaterEqual(swept, 2)
        self.assertEqual(first.serial_prefix_format, first.default_code)
        self.assertEqual(second.serial_prefix_format, second.default_code)

    def test_backfill_ignores_uncoded_products(self):
        """A service has no Internal Reference, so there is no prefix to give it."""
        service = self.env['product.template'].create({
            'name': "Installation", 'type': 'service',
        })

        self.env['product.template'].action_backfill_serial_prefix()

        self.assertFalse(service.serial_prefix_format)

    def test_backfill_requires_inventory_manager(self):
        product = self._make_product()
        user = self.env['res.users'].create({
            'name': "Stock User", 'login': 'stock_user_backfill',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        with self.assertRaises(AccessError):
            product.with_user(user).action_backfill_serial_prefix()

    # -- the shape the batch layer will rely on ------------------------------

    def test_generated_names_keep_the_prefix_across_a_batch(self):
        """The receipt wizard expands one serial into a run with
        generate_lot_names, which increments the last digit run. Pins that the
        Internal Reference survives that expansion."""
        product = self._make_product()
        first = product.lot_sequence_id.next_by_id()

        names = self.env['stock.lot'].generate_lot_names(first, 5)

        self.assertEqual(
            [entry['lot_name'] for entry in names],
            ['ZIZT001000001', 'ZIZT001000002', 'ZIZT001000003',
             'ZIZT001000004', 'ZIZT001000005'],
        )
        self.assertTrue(all(len(entry['lot_name']) == 13 for entry in names))
