from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestItemCode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'FG',
        })
        cls.raw_material = cls.env['inventory.category'].create({
            'name': "Raw Material", 'code': 'RM',
        })
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'HA',
        })
        cls.spare_part = cls.env['inventory.type'].create({
            'name': "Spare Part", 'code': 'SP',
        })
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'IN',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'FT', 'parent_id': cls.induction.id,
        })

    def _make_product(self, name, inv_category, inv_type, category=None, **extra):
        values = {
            'name': name,
            'inventory_category_id': inv_category.id,
            'inventory_type_id': inv_type.id,
            'categ_id': (category or self.flat_top).id,
        }
        values.update(extra)
        return self.env['product.template'].create(values)

    # -- generation ---------------------------------------------------------

    def test_codes_generated_with_expected_shape(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        self.assertEqual(product.item_code, 'FGHAINFT001')
        self.assertEqual(product.default_code, 'INFT001')
        # Four two-character segments here, but only the last two are fixed:
        # see test_free_length_classification_codes_are_accepted.
        self.assertEqual(len(product.item_code), 11)
        self.assertEqual(len(product.default_code), 7)
        self.assertNotIn('-', product.item_code)
        self.assertNotIn('-', product.default_code)

    def test_internal_reference_is_last_seven_of_item_code(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        self.assertEqual(product.default_code, product.item_code[-7:])

    def test_sequence_does_not_restart_across_category_type_combinations(self):
        """Regression test for the defect this build fixes.

        The counter is scoped to the leaf product category, not to the full
        four-segment combination. Two products sharing IN/FT under different
        Category/Type combinations must not both reach 001, or their Internal
        References would collide.
        """
        first = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        second = self._make_product("Element", self.raw_material, self.spare_part)

        self.assertEqual(first.item_code, 'FGHAINFT001')
        self.assertEqual(second.item_code, 'RMSPINFT002')
        self.assertEqual(first.default_code, 'INFT001')
        self.assertEqual(second.default_code, 'INFT002')
        self.assertNotEqual(first.default_code, second.default_code)

    def test_sequence_is_independent_per_leaf_category(self):
        other_leaf = self.env['product.category'].create({
            'name': "Ceramic Top", 'code': 'CT', 'parent_id': self.induction.id,
        })
        first = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        second = self._make_product(
            "Ceramic", self.finished_goods, self.home_appliance, category=other_leaf,
        )
        self.assertEqual(first.default_code, 'INFT001')
        self.assertEqual(second.default_code, 'INCT001')

    def test_free_length_classification_codes_are_accepted(self):
        """Inventory Category and Type codes are open: the item code follows them."""
        consumable = self.env['inventory.category'].create({
            'name': "Consumable", 'code': 'C',
        })
        packaging = self.env['inventory.type'].create({
            'name': "Packaging Material", 'code': 'PKGMAT',
        })
        product = self._make_product("Carton", consumable, packaging)

        self.assertEqual(product.item_code, 'CPKGMATINFT001')
        self.assertEqual(product.default_code, 'INFT001')

    def test_internal_reference_stays_seven_whatever_the_segments(self):
        """Only the product category segments feed the Internal Reference, so its
        length does not move with the classification codes."""
        long_category = self.env['inventory.category'].create({
            'name': "Semi Finished", 'code': 'SEMIFINISHED',
        })
        product = self._make_product("Frame", long_category, self.spare_part)

        self.assertEqual(len(product.default_code), 7)
        self.assertEqual(product.default_code, product.item_code[-7:])
        self.assertTrue(product.item_code.startswith('SEMIFINISHEDSP'))

    def test_services_are_not_classified(self):
        service = self.env['product.template'].create({
            'name': "Installation", 'type': 'service',
        })
        self.assertFalse(service.item_code)

    # -- refusals -----------------------------------------------------------

    def test_missing_classification_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['product.template'].create({
                'name': "Unclassified", 'categ_id': self.flat_top.id,
            })

    def test_top_level_category_is_refused(self):
        with self.assertRaises(ValidationError):
            self._make_product(
                "Cooker", self.finished_goods, self.home_appliance,
                category=self.induction,
            )

    def test_uncoded_category_is_refused(self):
        uncoded = self.env['product.category'].create({
            'name': "Uncoded", 'parent_id': self.induction.id,
        })
        with self.assertRaises(ValidationError):
            self._make_product(
                "Cooker", self.finished_goods, self.home_appliance, category=uncoded,
            )

    def test_malformed_code_is_refused(self):
        """Length is open, but the character set is not: the code is concatenated
        straight into the item code."""
        for bad in ('A-B', 'A B', 'A/B'):
            with self.subTest(code=bad), self.assertRaises(ValidationError):
                self.env['inventory.category'].create({'name': "Bad", 'code': bad})

    def test_product_category_code_must_stay_two_characters(self):
        """The two product category segments scope the sequence, so they keep a
        fixed width even though the classification codes no longer do."""
        for bad in ('X', 'XYZ'):
            with self.subTest(code=bad), self.assertRaises(ValidationError):
                self.env['product.category'].create({
                    'name': "Bad", 'code': bad, 'parent_id': self.induction.id,
                })

    def test_third_category_level_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env['product.category'].create({
                'name': "Too Deep", 'code': 'TD', 'parent_id': self.flat_top.id,
            })

    def test_duplicate_segment_code_is_refused(self):
        with self.assertRaises(Exception):
            with self.cr.savepoint():
                self.env['inventory.category'].create({'name': "Clash", 'code': 'FG'})
                self.env.flush_all()

    def test_sequence_exhaustion_raises_cleanly(self):
        sequence = self.env['product.template']._get_sequence('INFT')
        sequence.sudo().write({'number_next': 1000})
        with self.assertRaises(UserError):
            self._make_product("Overflow", self.finished_goods, self.home_appliance)

    # -- protection ---------------------------------------------------------

    def test_code_is_normalised_to_uppercase(self):
        record = self.env['inventory.category'].create({'name': "Trade", 'code': 'tr'})
        self.assertEqual(record.code, 'TR')

    def test_blank_code_is_stored_as_null(self):
        category = self.env['product.category'].create({'name': "Blank", 'code': ''})
        self.assertFalse(category.code)

    def test_classification_locked_once_code_issued(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        with self.assertRaises(UserError):
            product.inventory_category_id = self.raw_material

    def test_segment_code_locked_once_used(self):
        self._make_product("Cooker", self.finished_goods, self.home_appliance)
        with self.assertRaises(ValidationError):
            self.finished_goods.code = 'XX'

    def test_unused_segment_code_can_still_change(self):
        self.raw_material.code = 'RW'
        self.assertEqual(self.raw_material.code, 'RW')

    def test_regenerate_requires_inventory_manager(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        user = self.env['res.users'].create({
            'name': "Stock User", 'login': 'stock_user_item_code',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        with self.assertRaises(AccessError):
            product.with_user(user).action_regenerate_item_code()

    def test_regenerate_issues_a_new_number(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        original = product.item_code
        product.action_regenerate_item_code()
        self.assertNotEqual(product.item_code, original)
        self.assertEqual(product.default_code, product.item_code[-7:])

    def test_regenerate_is_logged_in_the_chatter(self):
        """The superseded code may be printed already, so it must stay traceable."""
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        before = product.message_ids
        product.action_regenerate_item_code()

        posted = product.message_ids - before
        self.assertTrue(posted, "regeneration must leave a log note")

        tracked = posted.tracking_value_ids
        by_field = {value.field_id.name: value for value in tracked}
        self.assertIn('item_code', by_field, "the item code change must be tracked")
        self.assertEqual(by_field['item_code'].old_value_char, 'FGHAINFT001')
        self.assertEqual(by_field['item_code'].new_value_char, product.item_code)

        self.assertIn('default_code', by_field, "the Internal Reference change must be tracked")
        self.assertEqual(by_field['default_code'].old_value_char, 'INFT001')
        self.assertEqual(by_field['default_code'].new_value_char, product.default_code)

    # -- duplication --------------------------------------------------------

    def test_duplicate_gets_its_own_codes(self):
        """default_code has no copy=False in core, so a duplicate would inherit the
        original's Internal Reference if generation did not overwrite it."""
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        duplicate = product.copy()

        self.assertEqual(product.item_code, 'FGHAINFT001')
        self.assertEqual(duplicate.item_code, 'FGHAINFT002')
        self.assertNotEqual(duplicate.default_code, product.default_code)
        self.assertEqual(duplicate.default_code, 'INFT002')

    def test_duplicate_keeps_the_classification(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        duplicate = product.copy()
        self.assertEqual(duplicate.inventory_category_id, product.inventory_category_id)
        self.assertEqual(duplicate.inventory_type_id, product.inventory_type_id)
        self.assertEqual(duplicate.categ_id, product.categ_id)

    def test_repeated_duplication_stays_unique(self):
        product = self._make_product("Cooker", self.finished_goods, self.home_appliance)
        copies = product + product.copy() + product.copy() + product.copy()
        references = copies.mapped('default_code')
        self.assertEqual(len(set(references)), 4, "duplicates must not share an Internal Reference")
        self.assertEqual(sorted(references), ['INFT001', 'INFT002', 'INFT003', 'INFT004'])

    # -- bulk creation and upload -------------------------------------------

    def test_batch_create_numbers_each_record(self):
        products = self.env['product.template'].create([
            {
                'name': "Cooker %s" % index,
                'inventory_category_id': self.finished_goods.id,
                'inventory_type_id': self.home_appliance.id,
                'categ_id': self.flat_top.id,
            }
            for index in range(5)
        ])
        references = products.mapped('default_code')
        self.assertEqual(references, ['INFT00%s' % n for n in range(1, 6)])
        self.assertEqual(len(set(products.mapped('item_code'))), 5)

    def test_bulk_upload_via_import(self):
        """Mirrors a CSV/XLSX import, which goes through load() rather than create()."""
        result = self.env['product.template'].load(
            ['name', 'inventory_category_id', 'inventory_type_id', 'categ_id'],
            [
                ["Cooker A", "Finished Goods", "Home Appliance", "Induction / Flat Top"],
                ["Cooker B", "Finished Goods", "Home Appliance", "Induction / Flat Top"],
                ["Element A", "Raw Material", "Spare Part", "Induction / Flat Top"],
            ],
        )
        self.assertFalse(result['messages'], "import reported problems: %s" % result['messages'])
        self.assertEqual(len(result['ids']), 3)

        products = self.env['product.template'].browse(result['ids'])
        self.assertEqual(
            products.mapped('item_code'),
            ['FGHAINFT001', 'FGHAINFT002', 'RMSPINFT003'],
        )
        self.assertEqual(
            products.mapped('default_code'), ['INFT001', 'INFT002', 'INFT003'],
        )
        self.assertEqual(len(set(products.mapped('default_code'))), 3)

    def test_bulk_upload_reports_unclassified_rows(self):
        result = self.env['product.template'].load(
            ['name', 'inventory_category_id', 'inventory_type_id', 'categ_id'],
            [["Unclassified", "", "", "Induction / Flat Top"]],
        )
        self.assertTrue(
            result['messages'],
            "an import row without a classification must be reported, not silently skipped",
        )
