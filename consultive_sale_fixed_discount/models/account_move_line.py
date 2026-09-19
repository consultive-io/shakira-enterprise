from odoo import api, fields, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    fixed_discount = fields.Monetary(
        string='Fixed Discount',
        default=0.0,
        currency_field='currency_id',
        help="Fixed amount discount on this line. Automatically calculates standard discount percentage."
    )

    @api.onchange('fixed_discount', 'price_unit', 'quantity')
    def _onchange_fixed_discount(self):
        for line in self:
            line_total = line.price_unit * line.quantity
            if line_total:
                discount_pct = (line.fixed_discount / line_total) * 100.0
            else:
                discount_pct = 0.0
            
            if abs(line.discount - discount_pct) > 0.0001:
                line.discount = discount_pct

    @api.onchange('discount', 'price_unit', 'quantity')
    def _onchange_discount_for_fixed(self):
        for line in self:
            line_total = line.price_unit * line.quantity
            fixed_discount_val = line_total * (line.discount / 100.0)
            
            if abs(line.fixed_discount - fixed_discount_val) > 0.0001:
                line.fixed_discount = fixed_discount_val
