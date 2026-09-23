# -*- coding: utf-8 -*-
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged, Form
from odoo.exceptions import ValidationError

@tagged('post_install', '-at_install')
class TestSaleFixedDiscount(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'list_price': 100.0,
            'type': 'consu',
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Test Partner'})

    def test_resolver_pure(self):
        """Test the pure _fd_resolve function"""
        Line = self.env['sale.order.line']
        
        # Test changed='fixed'
        self.assertEqual(Line._fd_resolve(100.0, 7.0, 0.0, 'fixed'), (100.0, 7.0, 93.0))
        
        # Test changed='net'
        self.assertEqual(Line._fd_resolve(100.0, 0.0, 90.0, 'net'), (100.0, 10.0, 90.0))
        
        # Test changed='net' when gross is 0
        self.assertEqual(Line._fd_resolve(0.0, 0.0, 50.0, 'net'), (50.0, 0.0, 50.0))
        
        # Test edge case (negative fixed discount should be blocked by constraint, but resolver just does math)
        self.assertEqual(Line._fd_resolve(100.0, -10.0, 0.0, 'fixed'), (100.0, -10.0, 110.0))

    def test_ui_matrix(self):
        """Test the matrix using Form to simulate UI onchanges"""
        so_form = Form(self.env['sale.order'])
        so_form.partner_id = self.partner
        
        # #1 Add product -> 100 list price
        with so_form.order_line.new() as line:
            line.product_id = self.product
            self.assertEqual(line.price_unit, 100.0)
            self.assertEqual(line.gross_price_unit, 100.0)
            self.assertEqual(line.fixed_discount, 0.0)
        
        # #2 Set Fixed = 7 -> net 93
        with so_form.order_line.edit(0) as line:
            line.fixed_discount = 7.0
            self.assertEqual(line.price_unit, 93.0)
            self.assertEqual(line.gross_price_unit, 100.0)
        
        # #3 Set Disc. Unit Price = 90 -> fixed 10
        with so_form.order_line.edit(0) as line:
            line.price_unit = 90.0
            self.assertEqual(line.fixed_discount, 10.0)
            self.assertEqual(line.gross_price_unit, 100.0)
            
        # #4 Set Unit Price = 120 (Fixed 7) -> net 113
        with so_form.order_line.edit(0) as line:
            line.fixed_discount = 7.0
            line.gross_price_unit = 120.0
            self.assertEqual(line.price_unit, 113.0)
            
        so = so_form.save()
        self.assertEqual(so.order_line.price_unit, 113.0)

    def test_invoicing(self):
        """Test that invoicing carries over the correct net price and informational fields"""
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_uom_qty': 3.0,
                    'fixed_discount': 7.0,
                })
            ]
        })
        self.assertEqual(so.order_line.price_unit, 93.0)
        so.action_confirm()
        
        so._create_invoices()
        invoice = so.invoice_ids
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        inv_line = invoice.invoice_line_ids[0]
        
        # Core flows
        self.assertEqual(inv_line.price_unit, 93.0)
        self.assertEqual(inv_line.price_subtotal, 279.0)
        
        # Informational fields
        self.assertEqual(inv_line.sale_gross_price_unit, 100.0)
        self.assertEqual(inv_line.sale_fixed_discount, 7.0)

    def test_constraints(self):
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })
        
        # Test fixed_discount > gross
        with self.assertRaises(ValidationError):
            self.env['sale.order.line'].create({
                'order_id': so.id,
                'product_id': self.product.id,
                'fixed_discount': 150.0,
            })
            
        # Test negative fixed discount
        with self.assertRaises(ValidationError):
            self.env['sale.order.line'].create({
                'order_id': so.id,
                'product_id': self.product.id,
                'fixed_discount': -10.0,
            })
