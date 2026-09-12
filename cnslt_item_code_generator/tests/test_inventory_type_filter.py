from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInventoryTypeFilter(TransactionCase):
    """An inventory category decides which inventory types its products may take."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'VH',
        })
        cls.spare_part = cls.env['inventory.type'].create({
            'name': "Spare Part", 'code': 'VS',
        })
        cls.packaging = cls.env['inventory.type'].create({
            'name': "Packaging", 'code': 'VP',
        })
        # Two categories allowing different types, and one that restricts nothing.
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'VF',
            'inventory_type_ids': [(6, 0, cls.home_appliance.ids)],
        })
        cls.components = cls.env['inventory.category'].create({
            'name': "Components", 'code': 'VC',
            'inventory_type_ids': [(6, 0, (cls.spare_part | cls.packaging).ids)],
        })
        cls.unrestricted = cls.env['inventory.category'].create({
            'name': "Misc", 'code': 'VM',
        })
        # The product category segments, which the item code needs but the
        # filter no longer has anything to do with.
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'VI',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'VT', 'parent_id': cls.induction.id,
        })

    def _form(self):
        form = Form(self.env['product.template'])
        form.name = "Cooker"
        form.categ_id = self.flat_top
        return form

    # -- what is offered ------------------------------------------------------

    def test_a_category_offers_only_its_types(self):
        form = self._form()
        form.inventory_category_id = self.components

        self.assertEqual(form.allowed_inventory_type_ids[:], self.spare_part | self.packaging)

    def test_an_unrestricted_category_offers_every_type(self):
        """Categories nobody has configured yet must keep working: the type is
        required on goods, so an empty picker would block product creation."""
        form = self._form()
        form.inventory_category_id = self.unrestricted

        offered = form.allowed_inventory_type_ids[:]
        self.assertLessEqual(self.home_appliance | self.spare_part | self.packaging, offered)
        self.assertEqual(offered, self.env['inventory.type'].search([]))

    def test_no_category_offers_nothing(self):
        """The category decides, so nothing is offered until one is chosen."""
        form = self._form()

        self.assertFalse(form.inventory_category_id)
        self.assertFalse(form.allowed_inventory_type_ids[:])

    # -- switching category ---------------------------------------------------

    def test_switching_category_drops_a_type_it_does_not_allow(self):
        form = self._form()
        form.inventory_category_id = self.finished_goods
        form.inventory_type_id = self.home_appliance

        form.inventory_category_id = self.components

        self.assertFalse(form.inventory_type_id)

    def test_switching_category_keeps_a_type_it_still_allows(self):
        form = self._form()
        form.inventory_category_id = self.components
        form.inventory_type_id = self.spare_part

        form.inventory_category_id = self.unrestricted

        self.assertEqual(form.inventory_type_id, self.spare_part)

    def test_clearing_the_category_clears_the_type(self):
        form = self._form()
        form.inventory_category_id = self.components
        form.inventory_type_id = self.spare_part

        form.inventory_category_id = self.env['inventory.category']

        self.assertFalse(form.inventory_type_id)

    def test_a_product_saved_through_the_filter_is_coded_as_usual(self):
        form = self._form()
        form.inventory_category_id = self.components
        form.inventory_type_id = self.packaging

        product = form.save()

        self.assertEqual(product.item_code, 'VCVPVIVT001')

    # -- the forms ------------------------------------------------------------

    def test_the_inventory_category_form_offers_the_types(self):
        arch = self.env['inventory.category'].get_view(
            self.env.ref('cnslt_item_code_generator.inventory_category_view_form').id, 'form',
        )['arch']

        self.assertIn('name="inventory_type_ids"', arch)

    def test_the_list_opens_that_form_rather_than_editing_in_place(self):
        """An editable list keeps the form shut, and the types are set there."""
        arch = self.env['inventory.category'].get_view(
            self.env.ref('cnslt_item_code_generator.inventory_category_view_list').id, 'list',
        )['arch']

        self.assertNotIn('editable', arch)
        self.assertIn('name="inventory_type_ids"', arch)

    def test_the_product_form_filters_the_type_picker(self):
        arch = self.env['product.template'].get_view(view_type='form')['arch']

        self.assertRegex(
            arch,
            r'<field name="inventory_type_id"[^>]*'
            r'domain="\[\(\'id\', \'in\', allowed_inventory_type_ids\)\]"',
        )
