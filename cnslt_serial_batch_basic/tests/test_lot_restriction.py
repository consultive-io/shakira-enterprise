from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLotRestriction(TransactionCase):
    """Test lot restriction on detailed operations depending on whether the receipt
    originates from a purchase order (purchase_id).
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
        cls.supplier = cls.env['res.partner'].create({'name': "Test Supplier"})
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1,
        )
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')

        cls.product = cls.env['product.template'].create({
            'name': "Charger Unit",
            'is_storable': True,
            'tracking': 'serial',
            'inventory_category_id': cls.finished_goods.id,
            'inventory_type_id': cls.home_appliance.id,
            'categ_id': cls.flat_top.id,
        })

    def test_manual_receipt_allows_manual_lot_editing(self):
        """Receipt without purchase_id has picking_has_purchase_id = False,
        allowing users to enter lots manually."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'partner_id': self.supplier.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        move = self.env['stock.move'].create({
            'product_id': self.product.product_variant_id.id,
            'product_uom_qty': 2,
            'picking_id': picking.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        picking.action_confirm()

        self.assertFalse(picking.purchase_id)
        self.assertFalse(move.picking_has_purchase_id)

        # Move line created manually
        line = self.env['stock.move.line'].create({
            'move_id': move.id,
            'picking_id': picking.id,
            'product_id': self.product.product_variant_id.id,
            'location_id': move.location_id.id,
            'location_dest_id': move.location_dest_id.id,
            'quantity': 1,
            'lot_name': 'MANUAL-SN-001',
        })
        self.assertFalse(line.picking_has_purchase_id)
        self.assertEqual(line.lot_name, 'MANUAL-SN-001')

    def test_po_receipt_locks_lot_editing(self):
        """Receipt with purchase_id has picking_has_purchase_id = True."""
        po = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.product_variant_id.id,
                    'product_qty': 2,
                    'price_unit': 100.0,
                }),
            ],
        })
        po.button_confirm()

        picking = po.picking_ids
        self.assertTrue(picking)
        self.assertEqual(picking.purchase_id, po)

        move = picking.move_ids
        self.assertTrue(move.picking_has_purchase_id)

        line = move.move_line_ids[:1]
        if line:
            self.assertTrue(line.picking_has_purchase_id)
        else:
            # Create a line with default context as in Detailed Operations popup
            new_line = self.env['stock.move.line'].with_context(
                default_picking_id=picking.id,
                default_move_id=move.id,
            ).create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': self.product.product_variant_id.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'quantity': 1,
            })
            self.assertTrue(new_line.picking_has_purchase_id)
