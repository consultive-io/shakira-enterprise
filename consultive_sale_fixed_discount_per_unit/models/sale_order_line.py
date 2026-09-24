# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    gross_price_unit = fields.Float(
        string="Unit Price",
        digits='Product Price',
        store=True,
        readonly=False,
        copy=True,
    )
    fixed_discount = fields.Float(
        string="Fixed Disc. / Unit",
        digits='Product Price',
        default=0.0,
        store=True,
        readonly=False,
        copy=True,
    )

    @api.model
    def _fd_resolve(self, gross, fixed, net, changed):
        """Single source of truth for fixed discount consistency.
        Returns (gross, fixed, net) with gross - fixed == net.
        changed ∈ {'gross', 'fixed', 'net'} — the value the user/caller supplied.
        """
        if changed == 'net':
            if not gross:  # no known original price (API line, zero-priced product)
                return net, 0.0, net
            return gross, gross - net, net
        return gross, fixed, gross - fixed

    def _get_fixed_discount_allowed(self):
        self.ensure_one()
        return not (
            self.display_type or 
            self.is_downpayment or 
            self.is_expense or
            self._is_global_discount() or
            getattr(self, 'product_type', '') == 'combo' or
            getattr(self, 'combo_item_id', False)
        )

    @api.constrains('gross_price_unit', 'fixed_discount', 'display_type', 'is_downpayment', 'is_expense')
    def _check_fixed_discount(self):
        for line in self:
            if line.fixed_discount < 0:
                raise ValidationError("Fixed discount cannot be negative.")
            if line.gross_price_unit > 0 and line.fixed_discount > line.gross_price_unit:
                raise ValidationError("Fixed discount cannot be greater than the unit price.")
            if line.gross_price_unit <= 0 and line.fixed_discount != 0.0:
                raise ValidationError("Fixed discount must be 0 for negative or zero-priced lines.")
            if line.fixed_discount != 0.0 and not line._get_fixed_discount_allowed():
                raise ValidationError("Fixed discount is not allowed on this type of line (e.g. section, down-payment, global discount, expense, or combo line).")

    def _reset_price_unit(self):
        super()._reset_price_unit()
        for line in self:
            if not line._get_fixed_discount_allowed():
                continue
            gross = line.price_unit
            gross, fixed, net = self._fd_resolve(gross, line.fixed_discount, 0.0, changed='fixed')
            line.gross_price_unit = gross
            line.price_unit = net
            line.technical_price_unit = net

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty')
    def _compute_price_unit(self):
        super()._compute_price_unit()
        for line in self:
            if not line._get_fixed_discount_allowed():
                continue
            if not line.product_id:
                line.gross_price_unit = 0.0
                line.fixed_discount = 0.0

    @api.onchange('gross_price_unit')
    def _onchange_gross_price_unit(self):
        for line in self:
            if not line._get_fixed_discount_allowed():
                continue
            gross = line.gross_price_unit or 0.0
            fixed = line.fixed_discount or 0.0
            _, _, net = self._fd_resolve(gross, fixed, 0.0, changed='fixed')
            line.price_unit = net
            # By not updating technical_price_unit, it differs from net, making the line manual.

    @api.onchange('fixed_discount')
    def _onchange_fixed_discount(self):
        for line in self:
            if not line._get_fixed_discount_allowed():
                continue
            gross = line.gross_price_unit or 0.0
            fixed = line.fixed_discount or 0.0
            _, _, net = self._fd_resolve(gross, fixed, 0.0, changed='fixed')
            line.price_unit = net
            # Keep the line pricelist-driven by syncing technical_price_unit
            line.technical_price_unit = net

    @api.onchange('price_unit')
    def _onchange_price_unit(self):
        for line in self:
            if not line._get_fixed_discount_allowed():
                continue
            gross = line.gross_price_unit or 0.0
            net = line.price_unit or 0.0
            _, fixed, _ = self._fd_resolve(gross, 0.0, net, changed='net')
            line.fixed_discount = fixed
            # It naturally becomes manual because technical_price_unit != new price_unit.

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Handle creation via API or other modules
            if 'gross_price_unit' in vals or 'fixed_discount' in vals:
                gross = vals.get('gross_price_unit', 0.0)
                fixed = vals.get('fixed_discount', 0.0)
                
                if 'price_unit' in vals:
                    net = vals['price_unit']
                    # Verify consistency if all three are provided
                    expected_net = gross - fixed if gross > 0 else net
                    # Using float_compare might be better, but strict equality for simple cases
                    if abs(expected_net - net) > 0.0001:
                        raise ValidationError("Inconsistent prices provided. gross_price_unit - fixed_discount must equal price_unit.")
                else:
                    _, _, net = self._fd_resolve(gross, fixed, 0.0, changed='fixed')
                    vals['price_unit'] = net
            elif 'price_unit' in vals:
                vals['gross_price_unit'] = vals['price_unit']
                vals['fixed_discount'] = 0.0
                
        return super().create(vals_list)

    def write(self, vals):
        # When writing price_unit only, e.g. from API
        if 'price_unit' in vals and 'gross_price_unit' not in vals and 'fixed_discount' not in vals:
            for line in self:
                gross = line.gross_price_unit
                net = vals['price_unit']
                _, fixed, _ = self._fd_resolve(gross, 0.0, net, changed='net')
                super(SaleOrderLine, line).write({'fixed_discount': fixed, 'price_unit': net})
            # Skip the main super() since we just wrote, or pop price_unit and continue?
            # It's cleaner to pop price_unit and let the loop handle it if we want to avoid multiple writes,
            # but write vals could have other fields.
            vals_copy = dict(vals)
            vals_copy.pop('price_unit')
            if vals_copy:
                return super().write(vals_copy)
            return True
            
        # If gross and fixed are written, or all three, ensure consistency
        if 'gross_price_unit' in vals or 'fixed_discount' in vals:
            gross = vals.get('gross_price_unit')
            fixed = vals.get('fixed_discount')
            net = vals.get('price_unit')
            # Let's let the constraints handle inconsistencies, but we should fill in price_unit if missing
            if 'price_unit' not in vals:
                # But it varies per line!
                # It's better to iterate
                res = True
                vals_to_write = dict(vals)
                if 'gross_price_unit' in vals_to_write:
                    del vals_to_write['gross_price_unit']
                if 'fixed_discount' in vals_to_write:
                    del vals_to_write['fixed_discount']
                
                for line in self:
                    line_gross = vals.get('gross_price_unit', line.gross_price_unit)
                    line_fixed = vals.get('fixed_discount', line.fixed_discount)
                    _, _, line_net = self._fd_resolve(line_gross, line_fixed, 0.0, changed='fixed')
                    super(SaleOrderLine, line).write({
                        'gross_price_unit': line_gross,
                        'fixed_discount': line_fixed,
                        'price_unit': line_net
                    })
                if vals_to_write:
                    res = super().write(vals_to_write)
                return res
            else:
                # all three present, let super handle and rely on constraint
                pass
                
        return super().write(vals)

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if 'sale_gross_price_unit' not in res:
            res['sale_gross_price_unit'] = self.gross_price_unit
        if 'sale_fixed_discount' not in res:
            res['sale_fixed_discount'] = self.fixed_discount
        return res
