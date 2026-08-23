from odoo import _, api, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _name = 'product.category'
    _inherit = ['product.category', 'inventory.code.segment.mixin']

    _code_uniq = models.Constraint(
        'unique(code)',
        "The Product Category code must be unique.",
    )

    @api.constrains('parent_id')
    def _check_category_depth(self):
        """Product categories supply two segments of the item code, so the tree is
        limited to two levels: a coded parent and its coded children."""
        for category in self:
            if category.parent_id and category.parent_id.parent_id:
                raise ValidationError(_(
                    "Product categories are limited to two levels. \"%(name)s\" would "
                    "sit at a third level under \"%(parent)s\".",
                    name=category.display_name,
                    parent=category.parent_id.display_name,
                ))

    def _code_is_in_use(self):
        self.ensure_one()
        # A parent category's code is in use once any product under any of its
        # children has been issued a code, so search the whole subtree.
        return bool(self.env['product.template'].sudo().search_count([
            ('categ_id', 'child_of', self.id),
            ('item_code', '!=', False),
        ], limit=1))
