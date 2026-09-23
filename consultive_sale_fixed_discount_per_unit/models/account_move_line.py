# -*- coding: utf-8 -*-
from odoo import fields, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    sale_gross_price_unit = fields.Float(
        string="Sale Original Price",
        digits='Product Price',
        readonly=True,
        copy=True,
    )
    sale_fixed_discount = fields.Float(
        string="Sale Fixed Disc.",
        digits='Product Price',
        readonly=True,
        copy=True,
    )
