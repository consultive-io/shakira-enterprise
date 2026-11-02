# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLotLabelReport(TransactionCase):
    """Test custom lot label paperformat and QWeb template override in cnslt_stock_lot_label."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.paperformat = cls.env.ref('cnslt_general_custom.paperformat_lot_label_42x33')
        cls.report_action = cls.env.ref('stock.action_report_lot_label')

        existing_product = cls.env['product.product'].search([('tracking', 'in', ('lot', 'serial'))], limit=1)
        if existing_product:
            cls.product = existing_product
        else:
            product_vals = {
                'name': 'Test Label Product',
                'is_storable': True,
                'tracking': 'lot',
            }
            if 'inventory.category' in cls.env:
                inv_cat = cls.env['inventory.category'].search([], limit=1) or cls.env['inventory.category'].create({'name': 'Test Cat', 'code': 'TC'})
                inv_type = cls.env['inventory.type'].search([], limit=1) or cls.env['inventory.type'].create({'name': 'Test Type', 'code': 'TT'})
                prod_cat = cls.env['product.category'].search([('parent_id', '!=', False)], limit=1)
                product_vals.update({
                    'inventory_category_id': inv_cat.id,
                    'inventory_type_id': inv_type.id,
                    'categ_id': prod_cat.id if prod_cat else cls.env.ref('product.product_category_all').id,
                })
            cls.product = cls.env['product.product'].create(product_vals)

        cls.lot = cls.env['stock.lot'].create({
            'name': 'LOT-TEST-001',
            'product_id': cls.product.id,
            'company_id': cls.env.company.id,
        })

    def test_paperformat_configuration(self):
        """Verify paperformat dimensions and configuration match specification."""
        self.assertTrue(self.paperformat.exists())
        self.assertEqual(self.paperformat.format, 'custom')
        self.assertEqual(self.paperformat.page_height, 32)
        self.assertEqual(self.paperformat.page_width, 42)
        self.assertEqual(self.paperformat.orientation, 'Portrait')
        self.assertEqual(self.paperformat.margin_top, 0.0)
        self.assertEqual(self.paperformat.margin_bottom, 0.0)
        self.assertEqual(self.paperformat.margin_left, 0.0)
        self.assertEqual(self.paperformat.margin_right, 0.0)
        self.assertEqual(self.paperformat.dpi, 96)
        self.assertTrue(self.paperformat.disable_shrinking)

    def test_report_action_paperformat_binding(self):
        """Verify stock.action_report_lot_label uses the custom paper format."""
        self.assertEqual(self.report_action.paperformat_id, self.paperformat)

    def test_report_rendering(self):
        """Verify report HTML rendering includes lot name, product name, and company/brand."""
        html_content, _ = self.env['ir.actions.report']._render_qweb_html(
            'stock.action_report_lot_label', [self.lot.id]
        )
        html_str = html_content.decode('utf-8')
        self.assertIn('LOT-TEST-001', html_str)
        self.assertIn(self.product.name, html_str)
        self.assertIn('STELLAR', html_str)
