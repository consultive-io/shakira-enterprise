from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReturnLotSelection(TransactionCase):
    """Return lines only offer serials of the original transfer not yet returned."""

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
        cls.product = cls.env['product.product'].create({
            'name': "Tracked Battery Pack",
            'is_storable': True,
            'tracking': 'serial',
            'inventory_category_id': cls.finished_goods.id,
            'inventory_type_id': cls.home_appliance.id,
            'categ_id': cls.induction.id,
        })
        cls.stock_loc = cls.env.ref('stock.stock_location_stock')
        cls.customer_loc = cls.env.ref('stock.stock_location_customers')
        cls.picking_type_out = cls.env.ref('stock.picking_type_out')
        cls.picking_type_in = cls.env.ref('stock.picking_type_in')

        # Create 3 serial numbers
        cls.lot1 = cls.env['stock.lot'].create({
            'name': "LOT000001",
            'product_id': cls.product.id,
        })
        cls.lot2 = cls.env['stock.lot'].create({
            'name': "LOT000002",
            'product_id': cls.product.id,
        })
        cls.lot_unrelated = cls.env['stock.lot'].create({
            'name': "LOT000003",
            'product_id': cls.product.id,
        })

        # Create and validate original delivery with LOT1 and LOT2
        cls.delivery = cls.env['stock.picking'].create({
            'picking_type_id': cls.picking_type_out.id,
            'location_id': cls.stock_loc.id,
            'location_dest_id': cls.customer_loc.id,
        })
        cls.move_out = cls.env['stock.move'].create({
            'name': cls.product.name,
            'product_id': cls.product.id,
            'product_uom': cls.product.uom_id.id,
            'product_uom_qty': 2.0,
            'picking_id': cls.delivery.id,
            'location_id': cls.stock_loc.id,
            'location_dest_id': cls.customer_loc.id,
        })
        cls.delivery.action_confirm()
        cls.env['stock.move.line'].create({
            'picking_id': cls.delivery.id,
            'move_id': cls.move_out.id,
            'product_id': cls.product.id,
            'product_uom_id': cls.product.uom_id.id,
            'quantity': 1.0,
            'lot_id': cls.lot1.id,
            'location_id': cls.stock_loc.id,
            'location_dest_id': cls.customer_loc.id,
        })
        cls.env['stock.move.line'].create({
            'picking_id': cls.delivery.id,
            'move_id': cls.move_out.id,
            'product_id': cls.product.id,
            'product_uom_id': cls.product.uom_id.id,
            'quantity': 1.0,
            'lot_id': cls.lot2.id,
            'location_id': cls.stock_loc.id,
            'location_dest_id': cls.customer_loc.id,
        })
        cls.delivery.button_validate()

    def _return(self, lot=None):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type_in.id,
            'location_id': self.customer_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'name': "Return",
            'product_id': self.product.id,
            'product_uom': self.product.uom_id.id,
            'product_uom_qty': 1.0,
            'picking_id': picking.id,
            'location_id': self.customer_loc.id,
            'location_dest_id': self.stock_loc.id,
            'origin_returned_move_id': self.move_out.id,
        })
        return self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'product_id': self.product.id,
            'product_uom_id': self.product.uom_id.id,
            'quantity': 1.0,
            'lot_id': lot.id if lot else False,
            'location_id': self.customer_loc.id,
            'location_dest_id': self.stock_loc.id,
        })

    def test_return_lots_limited_to_origin(self):
        line = self._return()
        self.assertEqual(line.return_lot_ids, self.lot1 | self.lot2)

    def test_unrelated_lot_rejected(self):
        with self.assertRaises(ValidationError):
            self._return(self.lot_unrelated)

    def test_already_returned_lot_excluded(self):
        line = self._return(self.lot1)
        line.move_id.picking_id.button_validate()
        self.assertEqual(self._return().return_lot_ids, self.lot2)
        with self.assertRaises(ValidationError):
            self._return(self.lot1)
