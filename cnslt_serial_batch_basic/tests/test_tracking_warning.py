from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTrackingWarning(TransactionCase):
    """Leaving serial or lot tracking while numbered stock is on hand.

    Driven through ``onchange()``, the same entry point the form uses, so the
    delegation from the template form to the variants is exercised rather than
    assumed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'WF',
        })
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'WH',
        })
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'WI',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'WT', 'parent_id': cls.induction.id,
        })
        cls.stock = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1,
        ).lot_stock_id

    def _make_product(self, tracking='serial'):
        return self.env['product.template'].create({
            'name': "Cooker",
            'is_storable': True,
            'tracking': tracking,
            'inventory_category_id': self.finished_goods.id,
            'inventory_type_id': self.home_appliance.id,
            'categ_id': self.flat_top.id,
        })

    def _stock_numbered(self, template, count, quantity=1):
        variant = template.product_variant_id
        for index in range(count):
            lot = self.env['stock.lot'].create({
                'name': '%s%06d' % (template.default_code, index + 1),
                'product_id': variant.id,
            })
            self.env['stock.quant']._update_available_quantity(
                variant, self.stock, quantity, lot_id=lot,
            )

    def _warning(self, record, tracking):
        result = record.onchange({'tracking': tracking}, ['tracking'], {'tracking': {}})
        return result.get('warning')

    def test_leaving_serial_with_serials_in_stock_warns(self):
        product = self._make_product('serial')
        self._stock_numbered(product, 3)

        warning = self._warning(product, 'none')

        self.assertTrue(warning)
        self.assertIn("3 units", warning['message'])
        self.assertIn("3 serial/lot numbers", warning['message'])

    def test_the_variant_form_warns_too(self):
        product = self._make_product('serial')
        self._stock_numbered(product, 2)

        self.assertTrue(self._warning(product.product_variant_id, 'none'))

    def test_leaving_lot_tracking_warns(self):
        product = self._make_product('lot')
        self._stock_numbered(product, 1, quantity=40)

        warning = self._warning(product, 'none')

        self.assertTrue(warning)
        self.assertIn("40 units", warning['message'])

    def test_serials_that_have_all_left_do_not_warn(self):
        """Issued but delivered: history, and it survives the change intact."""
        product = self._make_product('serial')
        self._stock_numbered(product, 2)
        variant = product.product_variant_id
        for quant in self.env['stock.quant'].search([('product_id', '=', variant.id)]):
            self.env['stock.quant']._update_available_quantity(
                variant, self.stock, -quant.quantity, lot_id=quant.lot_id,
            )

        self.assertFalse(self._warning(product, 'none'))

    def test_a_product_that_was_never_tracked_does_not_warn(self):
        product = self._make_product('none')

        self.assertFalse(self._warning(product, 'none'))

    def test_moving_between_serial_and_lot_adds_no_warning_of_ours(self):
        """Numbers stay visible either way; only By Quantity hides them.

        Core still shows its own untracked-stock warning here -- it checks for
        stock on hand, not whether that stock is already numbered -- so this
        asserts only that ours stays out of it.
        """
        product = self._make_product('serial')
        self._stock_numbered(product, 2)

        warning = self._warning(product, 'lot') or {}

        self.assertNotEqual(warning.get('title'), "Serial numbers in stock")

    def test_core_warning_in_the_other_direction_is_untouched(self):
        """Untracked stock becoming tracked is core's case and keeps its message."""
        product = self._make_product('none')
        self.env['stock.quant']._update_available_quantity(
            product.product_variant_id, self.stock, 5,
        )

        warning = self._warning(product, 'serial')

        self.assertTrue(warning)
        self.assertIn("have no lot/serial number", warning['message'])

    def test_the_change_itself_is_not_blocked(self):
        """Raw materials flipped to serial need this exact change to be fixed."""
        product = self._make_product('serial')
        self._stock_numbered(product, 2)

        product.tracking = 'none'

        self.assertEqual(product.tracking, 'none')
