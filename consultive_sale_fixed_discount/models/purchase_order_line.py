from odoo import api, fields, models

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    fixed_discount = fields.Monetary(
        string='Fixed Discount',
        default=0.0,
        currency_field='currency_id',
        help="Fixed amount discount on this line. Automatically calculates standard discount percentage."
    )

    @api.onchange('fixed_discount', 'price_unit', 'product_qty')
    def _onchange_fixed_discount(self):
        for line in self:
            line_total = line.price_unit * line.product_qty
            if line_total:
                discount_pct = (line.fixed_discount / line_total) * 100.0
            else:
                discount_pct = 0.0
            
            if abs(line.discount - discount_pct) > 0.0001:
                line.discount = discount_pct

    @api.onchange('discount', 'price_unit', 'product_qty')
    def _onchange_discount_for_fixed(self):
        for line in self:
            line_total = line.price_unit * line.product_qty
            fixed_discount_val = line_total * (line.discount / 100.0)
            
            if abs(line.fixed_discount - fixed_discount_val) > 0.0001:
                line.fixed_discount = fixed_discount_val

    def _prepare_account_move_line(self, move=False):
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move)
        res['fixed_discount'] = self.fixed_discount
        return res
