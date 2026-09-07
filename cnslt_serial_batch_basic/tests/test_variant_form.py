from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

# Buttons that call a method defined only on product.template.
TEMPLATE_ONLY_BUTTONS = (
    'action_regenerate_item_code',
    'action_resync_serial_counter',
)


@tagged('post_install', '-at_install')
class TestVariantFormButtons(TransactionCase):
    """The product variant form is a primary inherited copy of the product
    template form with the model switched to product.product, so anything added
    to that shared base is rendered on both.

    product.product delegates the template's fields through _inherits but not its
    methods. A button placed on the base therefore looks perfectly healthy on the
    variant form -- every field it references resolves -- and raises
    "The method 'product.product.<name>' does not exist" the moment it is
    clicked. This is a regression test for exactly that.
    """

    def _variant_form_arch(self):
        view = self.env['product.product'].get_view(
            view_id=self.env.ref('product.product_normal_form_view').id,
            view_type='form',
        )
        return etree.fromstring(view['arch'])

    def test_template_only_buttons_are_absent_from_the_variant_form(self):
        arch = self._variant_form_arch()
        for name in TEMPLATE_ONLY_BUTTONS:
            found = arch.xpath('//button[@name="%s"]' % name)
            self.assertFalse(
                found,
                "%s is rendered on the product.product form. The method is "
                "defined on product.template only, so clicking it raises "
                "AttributeError. Anchor the view to "
                "product.product_template_only_form_view instead of the shared "
                "product.product_template_form_view." % name,
            )

    def test_the_buttons_are_still_on_the_template_form(self):
        """The fix must not simply delete them."""
        view = self.env['product.template'].get_view(
            view_id=self.env.ref('product.product_template_only_form_view').id,
            view_type='form',
        )
        arch = etree.fromstring(view['arch'])
        for name in TEMPLATE_ONLY_BUTTONS:
            self.assertTrue(
                arch.xpath('//button[@name="%s"]' % name),
                "%s should still be available on the product template form." % name,
            )

    def test_a_variant_can_still_answer_for_its_template(self):
        """Belt and braces: anything that does reach a variant -- a server
        action, an automation, an RPC call -- is forwarded rather than failing."""
        for name in TEMPLATE_ONLY_BUTTONS + ('action_backfill_serial_prefix',):
            self.assertTrue(
                hasattr(type(self.env['product.product']), name),
                "product.product should forward %s to its template." % name,
            )


@tagged('post_install', '-at_install')
class TestVariantForwarding(TransactionCase):
    """Forwarding variant -> template is only safe because a coded product has
    exactly one variant. These pin the properties that make it so.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['inventory.category'].create({'name': "Finished", 'code': 'ZF'})
        cls.env['inventory.type'].create({'name': "Appliance", 'code': 'ZH'})
        parent = cls.env['product.category'].create({'name': "Induction", 'code': 'ZI'})
        cls.leaf = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'ZT', 'parent_id': parent.id,
        })
        cls.product = cls.env['product.template'].create({
            'name': "Cooker",
            'is_storable': True,
            'inventory_category_id': cls.env['inventory.category'].search(
                [('code', '=', 'ZF')], limit=1).id,
            'inventory_type_id': cls.env['inventory.type'].search(
                [('code', '=', 'ZH')], limit=1).id,
            'categ_id': cls.leaf.id,
        })

    def test_a_coded_product_has_exactly_one_variant(self):
        """The property the forwarding rests on. Multi-variant templates are
        refused a code, so variant and template are always 1:1 here."""
        self.assertEqual(len(self.product.product_variant_ids), 1)

    def test_forwarding_reaches_the_most_derived_override(self):
        """The variant must get the *guarded* regenerate from this module, not
        just the base implementation from the item code generator."""
        self.env['stock.lot'].create({
            'name': '%s000001' % self.product.default_code,
            'product_id': self.product.product_variant_id.id,
            'company_id': self.env.company.id,
        })

        with self.assertRaises(UserError):
            self.product.product_variant_id.action_regenerate_item_code()

        self.assertEqual(self.product.default_code, 'ZIZT001')

    def test_forwarding_preserves_the_access_check(self):
        """Forwarding must not become a way around the manager-only rule."""
        user = self.env['res.users'].create({
            'name': "Stock User", 'login': 'stock_user_variant_forward',
            'group_ids': [(6, 0, [self.env.ref('stock.group_stock_user').id])],
        })
        with self.assertRaises(AccessError):
            self.product.product_variant_id.with_user(user).action_resync_serial_counter()

    def test_forwarding_does_the_same_work_as_the_template(self):
        self.env['stock.lot'].create({
            'name': '%s000045' % self.product.default_code,
            'product_id': self.product.product_variant_id.id,
            'company_id': self.env.company.id,
        })
        self.assertTrue(self.product.serial_counter_drift)

        self.product.product_variant_id.action_resync_serial_counter()

        self.assertFalse(self.product.serial_counter_drift)
        self.assertEqual(self.product.lot_sequence_id.number_next_actual, 46)
