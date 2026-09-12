from odoo.exceptions import UserError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestGenerateSerialDialog(TransactionCase):
    """The Generate Serials/Lots dialog, entered where the dialog itself enters:
    action_generate_lot_line_vals, with the First SN box as it was left."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'YF',
        })
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'YH',
        })
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'YI',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'YT', 'parent_id': cls.induction.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1,
        )
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')

    def setUp(self):
        super().setUp()
        self.cooker = self.env['product.template'].create({
            'name': "Cooker",
            'is_storable': True,
            'tracking': 'serial',
            'inventory_category_id': self.finished_goods.id,
            'inventory_type_id': self.home_appliance.id,
            'categ_id': self.flat_top.id,
        })
        self.receipt = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        self.move = self.env['stock.move'].create({
            'product_id': self.cooker.product_variant_id.id,
            'product_uom_qty': 2,
            'picking_id': self.receipt.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        self.receipt.action_confirm()
        self.receipt.action_assign()

    def _context(self):
        """What the dialog sends along with the boxes."""
        return {
            'default_product_id': self.move.product_id.id,
            'default_location_id': self.move.location_id.id,
            'default_location_dest_id': self.move.location_dest_id.id,
            'default_tracking': 'serial',
            'default_quantity': 2,
            'default_company_id': self.move.company_id.id,
            'default_picking_id': self.receipt.id,
            'default_picking_type_id': self.receipt.picking_type_id.id,
            'default_move_id': self.move.id,
        }

    def test_generating_without_clicking_new_is_refused(self):
        """Blank numbers from nothing: "0", "1", "2", outside the series."""
        with self.assertRaisesRegex(UserError, "Click New"):
            self.move.action_generate_lot_line_vals(self._context(), 'generate', '', 2, '')

    def test_a_blank_of_spaces_is_refused_too(self):
        with self.assertRaisesRegex(UserError, "Click New"):
            self.move.action_generate_lot_line_vals(self._context(), 'generate', '   ', 2, '')

    def test_generating_after_new_still_works(self):
        first = self.cooker.lot_sequence_id.sudo().next_by_id()

        vals = self.move.action_generate_lot_line_vals(self._context(), 'generate', first, 2, '')

        self.assertEqual(
            [line['lot_name'] for line in vals],
            ['%s%06d' % (self.cooker.default_code, number) for number in (1, 2)],
        )

    # -- through the path the dialog really takes ------------------------------

    def _call_kw(self, mode, first_lot, count, lot_text=''):
        """What the web client does: call_kw on the model, not on a record.

        Worth going through rather than calling the method directly, because
        this is where losing @api.model shows: call_kw would read the first
        argument as record ids and land every later one in the wrong parameter,
        which a direct call cannot reveal.
        """
        return call_kw(
            self.env['stock.move'], 'action_generate_lot_line_vals',
            [self._context(), mode, first_lot, count, lot_text], {},
        )

    def test_the_dialog_path_refuses_a_blank_first_serial(self):
        with self.assertRaisesRegex(UserError, "Click New"):
            self._call_kw('generate', '', 2)

    def test_the_dialog_path_generates_after_new(self):
        first = self.cooker.lot_sequence_id.sudo().next_by_id()

        vals = self._call_kw('generate', first, 2)

        self.assertEqual(
            [line['lot_name'] for line in vals],
            ['%s%06d' % (self.cooker.default_code, number) for number in (1, 2)],
        )

    def test_importing_a_list_is_left_alone(self):
        """The guard is about the First SN box, which import mode does not use."""
        names = "%s000001\n%s000002" % (self.cooker.default_code, self.cooker.default_code)

        vals = self.move.action_generate_lot_line_vals(self._context(), 'import', '', 0, names)

        self.assertEqual(len(vals), 2)
