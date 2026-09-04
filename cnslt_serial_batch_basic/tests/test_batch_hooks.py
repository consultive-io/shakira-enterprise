from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBatchHooks(TransactionCase):
    """Batches are made as a consequence of validating a receipt or closing a
    manufacturing order, never by hand. Both entry points can return a wizard
    without having validated anything, and confirming that wizard re-enters the
    same method, so the hooks have to be both late and re-entrant.
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
        cls.cooker = cls._make_product("Cooker", default_warranty_months=24)
        cls.griddle = cls._make_product("Griddle", default_warranty_months=6)

        cls.supplier = cls.env['res.partner'].create({'name': "Guangdong Appliance"})
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.env.company.id)], limit=1,
        )
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')

    @classmethod
    def _make_product(cls, name, **extra):
        values = {
            'name': name,
            'is_storable': True,
            'inventory_category_id': cls.finished_goods.id,
            'inventory_type_id': cls.home_appliance.id,
            'categ_id': cls.flat_top.id,
        }
        values.update(extra)
        return cls.env['product.template'].create(values)

    # -- receipts -----------------------------------------------------------

    def _make_receipt(self, lines):
        """lines: [(product_template, quantity)]"""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'partner_id': self.supplier.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': self.warehouse.lot_stock_id.id,
        })
        for product, quantity in lines:
            self.env['stock.move'].create({
                'product_id': product.product_variant_id.id,
                'product_uom_qty': quantity,
                'picking_id': picking.id,
                'location_id': self.supplier_location.id,
                'location_dest_id': self.warehouse.lot_stock_id.id,
            })
        picking.action_confirm()
        return picking

    def _assign_serials(self, picking, product, count, start=1):
        """Stand in for the Generate Serial Numbers dialog."""
        move = picking.move_ids.filtered(
            lambda m: m.product_id == product.product_variant_id
        )
        move.move_line_ids.unlink()
        prefix = product.default_code
        for index in range(start, start + count):
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': product.product_variant_id.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'quantity': 1,
                'lot_name': '%s%06d' % (prefix, index),
            })
        return move

    def test_a_receipt_produces_one_batch_holding_its_serials(self):
        picking = self._make_receipt([(self.cooker, 3)])
        self._assign_serials(picking, self.cooker, 3)

        picking.button_validate()

        self.assertEqual(picking.state, 'done')
        batches = self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        self.assertEqual(len(batches), 1)

        batch = batches
        self.assertEqual(batch.product_id, self.cooker.product_variant_id)
        self.assertEqual(batch.source_type, 'receipt')
        self.assertEqual(batch.partner_id, self.supplier)
        self.assertEqual(batch.lot_count, 3)
        self.assertEqual(
            batch.date, fields.Date.context_today(picking, picking.date_done),
        )

    def test_warranty_is_snapshotted_from_the_product(self):
        picking = self._make_receipt([(self.cooker, 1)])
        self._assign_serials(picking, self.cooker, 1)
        picking.button_validate()

        batch = self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        self.assertEqual(batch.warranty_months, 24)
        self.assertTrue(batch.warranty_end_date)

        # The product's policy changes; units already received keep their terms.
        self.cooker.default_warranty_months = 6
        self.assertEqual(batch.warranty_months, 24)

    def test_each_product_on_a_receipt_gets_its_own_batch(self):
        """A batch describes one product: two products means two batches, each
        with its own warranty."""
        picking = self._make_receipt([(self.cooker, 2), (self.griddle, 2)])
        self._assign_serials(picking, self.cooker, 2)
        self._assign_serials(picking, self.griddle, 2)

        picking.button_validate()

        batches = self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        self.assertEqual(len(batches), 2)
        by_product = {batch.product_id: batch for batch in batches}
        self.assertEqual(by_product[self.cooker.product_variant_id].warranty_months, 24)
        self.assertEqual(by_product[self.griddle.product_variant_id].warranty_months, 6)

    def test_serials_carry_the_warranty_of_their_own_batch(self):
        picking = self._make_receipt([(self.cooker, 1), (self.griddle, 1)])
        self._assign_serials(picking, self.cooker, 1)
        self._assign_serials(picking, self.griddle, 1)
        picking.button_validate()

        lots = self.env['stock.lot'].search([('batch_id.picking_id', '=', picking.id)])
        for lot in lots:
            self.assertEqual(lot.batch_id.product_id, lot.product_id)
            self.assertEqual(lot.warranty_end_date, lot.batch_id.warranty_end_date)

    def test_revalidating_creates_no_second_batch(self):
        """Confirming a wizard re-enters button_validate, so the hook must be
        safe to run twice."""
        picking = self._make_receipt([(self.cooker, 2)])
        self._assign_serials(picking, self.cooker, 2)
        picking.button_validate()

        before = self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        picking._create_serial_batches()
        after = self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])

        self.assertEqual(before, after)
        self.assertEqual(len(after), 1)
        self.assertEqual(after.lot_count, 2)

    def test_an_unvalidated_receipt_produces_no_batch(self):
        """The hook runs after super() but only for pickings that actually reached
        'done' -- core can return a wizard without validating anything."""
        picking = self._make_receipt([(self.cooker, 2)])
        self._assign_serials(picking, self.cooker, 2)

        self.assertNotEqual(picking.state, 'done')
        self.assertFalse(
            self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        )

    def test_a_backorder_gets_its_own_batch(self):
        """The remaining goods arrive on a different day, so their warranty runs
        from then. Merging them into the first batch would backdate it."""
        picking = self._make_receipt([(self.cooker, 5)])
        self._assign_serials(picking, self.cooker, 2)

        action = picking.button_validate()
        # Core offers a backorder; take it.
        if isinstance(action, dict) and action.get('res_model') == 'stock.backorder.confirmation':
            wizard = self.env[action['res_model']].with_context(action['context']).create({})
            wizard.process()

        self.assertEqual(picking.state, 'done')
        backorder = self.env['stock.picking'].search([('backorder_id', '=', picking.id)])
        self.assertTrue(backorder, "expected a backorder for the undelivered units")

        self._assign_serials(backorder, self.cooker, 3, start=3)
        backorder.button_validate()

        first = self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        second = self.env['inventory.serial.batch'].search([('picking_id', '=', backorder.id)])

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first, second)
        self.assertEqual(first.lot_count, 2)
        self.assertEqual(second.lot_count, 3)

    # -- manufacturing ------------------------------------------------------

    def _make_production(self, product, serial):
        production = self.env['mrp.production'].create({
            'product_id': product.product_variant_id.id,
            'product_qty': 1,
            'product_uom_id': product.uom_id.id,
        })
        production.action_confirm()
        production.qty_producing = 1
        production.lot_producing_ids = self.env['stock.lot'].create({
            'name': serial,
            'product_id': product.product_variant_id.id,
            'company_id': self.env.company.id,
        })
        return production

    def test_a_manufacturing_order_produces_its_own_batch(self):
        production = self._make_production(self.cooker, 'ZIZT001000901')

        production.button_mark_done()

        self.assertEqual(production.state, 'done')
        batch = self.env['inventory.serial.batch'].search(
            [('production_id', '=', production.id)],
        )
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch.source_type, 'manufacturing')
        self.assertEqual(batch.product_id, self.cooker.product_variant_id)
        self.assertFalse(batch.picking_id)
        self.assertEqual(batch.warranty_months, 24)
        self.assertEqual(batch.lot_count, 1)
        self.assertEqual(
            batch.date, fields.Date.context_today(production, production.date_finished),
        )

    def test_two_manufacturing_orders_do_not_share_a_batch(self):
        """Split or repeated runs finish at their own times, so each is its own
        batch with its own date."""
        first = self._make_production(self.cooker, 'ZIZT001000902')
        first.button_mark_done()
        second = self._make_production(self.cooker, 'ZIZT001000903')
        second.button_mark_done()

        Batch = self.env['inventory.serial.batch']
        first_batch = Batch.search([('production_id', '=', first.id)])
        second_batch = Batch.search([('production_id', '=', second.id)])

        self.assertTrue(first_batch and second_batch)
        self.assertNotEqual(first_batch, second_batch)

    def test_remarking_a_production_creates_no_second_batch(self):
        production = self._make_production(self.cooker, 'ZIZT001000904')
        production.button_mark_done()

        before = self.env['inventory.serial.batch'].search(
            [('production_id', '=', production.id)],
        )
        production._create_serial_batches()
        after = self.env['inventory.serial.batch'].search(
            [('production_id', '=', production.id)],
        )

        self.assertEqual(before, after)
        self.assertEqual(len(after), 1)

    def test_an_unfinished_production_produces_no_batch(self):
        production = self._make_production(self.cooker, 'ZIZT001000905')

        self.assertNotEqual(production.state, 'done')
        self.assertFalse(
            self.env['inventory.serial.batch'].search([('production_id', '=', production.id)])
        )

    # -- not batched --------------------------------------------------------

    def test_outgoing_transfers_are_not_batched(self):
        """A batch records where goods came from. Shipping them out is not that."""
        delivery = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        self.assertFalse(
            self.env['inventory.serial.batch'].search([('picking_id', '=', delivery.id)])
        )

    def test_untracked_goods_produce_no_batch(self):
        """Nothing to group: without serials there is nothing to hang a date on."""
        plain = self._make_product("Bracket", is_storable=True)
        plain.tracking = 'none'
        picking = self._make_receipt([(plain, 4)])
        picking.move_ids.quantity = 4

        picking.button_validate()

        self.assertEqual(picking.state, 'done')
        self.assertFalse(
            self.env['inventory.serial.batch'].search([('picking_id', '=', picking.id)])
        )
