from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSerialCounterDrift(TransactionCase):
    """The counter and the issued serials are two different sources of truth.

    They part company when a serial is created without the sequence being asked
    for it -- a hand-typed number in the receipt wizard, or an import. Only the
    counter falling *behind* matters: the next draw then collides with a serial
    already on a unit, and the receipt is refused.
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

    def _make_lot(self, product, name):
        return self.env['stock.lot'].create({
            'name': name,
            'product_id': product.product_variant_id.id,
            'company_id': self.env.company.id,
        })

    # -- what was issued ----------------------------------------------------

    def test_no_serials_yet(self):
        product = self._make_product()
        self.assertFalse(product.last_serial_used)
        self.assertFalse(product.serial_counter_drift)

    def test_last_serial_used_is_the_highest_not_the_newest(self):
        """They agree on a healthy product and diverge when something is wrong;
        it is the highest that decides whether the next draw collides."""
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000009')
        self._make_lot(product, 'ZIZT001000003')   # created later, lower number

        self.assertEqual(product.last_serial_used, 'ZIZT001000009')

    def test_serials_of_another_shape_are_ignored(self):
        """Hand-entered and migrated serials sit outside the scheme. They are the
        case this tool investigates, so they must not break it."""
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000004')
        self._make_lot(product, 'LEGACY-778')
        self._make_lot(product, 'ZIZT001ABCDEF')

        self.assertEqual(product.last_serial_used, 'ZIZT001000004')

    # -- drift --------------------------------------------------------------

    def test_a_healthy_product_reports_no_drift(self):
        product = self._make_product()
        issued = product.lot_sequence_id.next_by_id()
        self._make_lot(product, issued)

        self.assertFalse(product.serial_counter_drift)

    def test_a_counter_left_behind_is_flagged(self):
        """A serial typed by hand does not advance the counter, so the next draw
        would reissue a number already on a unit."""
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000045')

        self.assertEqual(product.lot_sequence_id.number_next_actual, 1)
        self.assertTrue(product.serial_counter_drift)
        self.assertIn('ZIZT001000046', product.serial_counter_message)

    def test_a_counter_running_ahead_is_not_flagged(self):
        """Gaps are harmless -- a discarded 'New', a deleted lot -- and flagging
        them would cry wolf on ordinary use."""
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000001')
        product.lot_sequence_id.sudo().number_next_actual = 50

        self.assertFalse(product.serial_counter_drift)

    # -- resync -------------------------------------------------------------

    def test_resync_moves_the_counter_past_the_highest(self):
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000045')
        self.assertTrue(product.serial_counter_drift)

        product.action_resync_serial_counter()

        self.assertEqual(product.lot_sequence_id.number_next_actual, 46)
        self.assertFalse(product.serial_counter_drift)
        self.assertEqual(product.lot_sequence_id.next_by_id(), 'ZIZT001000046')

    def test_resync_is_logged_in_the_chatter(self):
        """Editing the sequence by hand leaves no trace; this must."""
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000045')
        before = product.message_ids

        product.action_resync_serial_counter()

        posted = product.message_ids - before
        self.assertTrue(posted, "a resync must leave a note on the product")
        self.assertIn('46', posted[0].body)

    def test_resync_does_nothing_when_already_aligned(self):
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000045')
        product.action_resync_serial_counter()

        self.assertFalse(product.action_resync_serial_counter())

    def test_resync_leaves_a_hand_configured_sequence_alone(self):
        manual = self.env['ir.sequence'].create({
            'name': "Hand Built", 'code': 'x_manual_serial',
            'prefix': 'MANUAL', 'padding': 4, 'company_id': False,
        })
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000045')
        product.lot_sequence_id = manual

        product.action_resync_serial_counter()

        self.assertEqual(manual.number_next_actual, 1)

    def test_resync_requires_inventory_manager(self):
        product = self._make_product()
        user = self.env['res.users'].create({
            'name': "Stock User", 'login': 'stock_user_resync',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        with self.assertRaises(AccessError):
            product.with_user(user).action_resync_serial_counter()

    # -- regeneration guard (work item 6) -----------------------------------

    def test_regenerate_is_refused_once_serials_exist(self):
        """The issued serials are printed on units that have shipped; a new code
        would leave them carrying a reference the product no longer has."""
        product = self._make_product()
        self._make_lot(product, 'ZIZT001000001')

        with self.assertRaises(UserError):
            product.action_regenerate_item_code()

        self.assertEqual(product.default_code, 'ZIZT001')

    def test_regenerate_still_works_before_any_serial(self):
        """The button remains usable for its real purpose: correcting a
        misclassification caught before anything shipped."""
        product = self._make_product()

        product.action_regenerate_item_code()

        self.assertEqual(product.default_code, 'ZIZT002')

    def test_a_mixed_selection_is_refused_whole(self):
        """Checked across the recordset first, so nothing half-applies."""
        clean = self._make_product("Cooker")
        blocked = self._make_product("Griddle")
        self._make_lot(blocked, '%s000001' % blocked.default_code)
        original = clean.default_code

        with self.assertRaises(UserError):
            (clean + blocked).action_regenerate_item_code()

        self.assertEqual(clean.default_code, original)
