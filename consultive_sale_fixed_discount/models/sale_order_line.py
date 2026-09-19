from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    fixed_discount = fields.Monetary(
        string='Fixed Discount',
        compute='_compute_fixed_discount',
        inverse='_inverse_fixed_discount',
        store=True,
        currency_field='currency_id',
        help="Fixed amount discount on this line. Automatically calculates standard discount percentage."
    )

    @api.depends('discount', 'price_unit', 'product_uom_qty')
    def _compute_fixed_discount(self):
        for line in self:
            line_total = line.price_unit * line.product_uom_qty
            fixed_discount_val = line_total * (line.discount / 100.0)
            if abs(line.fixed_discount - fixed_discount_val) > 0.0001:
                line.fixed_discount = fixed_discount_val

    def _inverse_fixed_discount(self):
        for line in self:
            line_total = line.price_unit * line.product_uom_qty
            if line_total:
                discount_pct = (line.fixed_discount / line_total) * 100.0
            else:
                discount_pct = 0.0
            
            if abs(line.discount - discount_pct) > 0.0001:
                line.discount = discount_pct

    @api.onchange('fixed_discount')
    def _onchange_fixed_discount_ui(self):
        # This provides immediate UI feedback before saving
        for line in self:
            line_total = line.price_unit * line.product_uom_qty
            if line_total:
                discount_pct = (line.fixed_discount / line_total) * 100.0
            else:
                discount_pct = 0.0
            
            if abs(line.discount - discount_pct) > 0.0001:
                line.discount = discount_pct

    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        res['fixed_discount'] = self.fixed_discount
        return res
