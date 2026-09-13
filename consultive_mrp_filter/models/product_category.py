from odoo import models, fields

class ProductCategory(models.Model):
    _inherit = 'product.category'

    is_mo_component = fields.Boolean(
        string='Is MO Component',
        help='If checked, products in this category will be available for selection as raw materials in BOM and MO.',
        default=False
    )
