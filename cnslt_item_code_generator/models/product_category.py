from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _name = 'product.category'
    _inherit = ['product.category', 'inventory.code.segment.mixin']

    # The sequence is scoped to the parent and child codes run together, so these
    # two segments stay fixed-width: were they free-length, "A" + "BC" and "AB" +
    # "C" would read as the same scope and the Internal Reference would no longer
    # say which category it came from.
    _code_length = 2

    _code_uniq = models.Constraint(
        'unique(code)',
        "The Product Category code must be unique.",
    )

    # No size on the column: it would truncate an over-long code before
    # _check_code_format could reject it.
    code = fields.Char(
        help="Two-character segment used to assemble the item code. "
             "Uppercase letters and digits only.",
    )
    # Only meaningful on a child category: products can only be coded under one
    # (see _check_classification_ready on product.template), so that is where
    # the form offers it.
    inventory_type_ids = fields.Many2many(
        'inventory.type', 'product_category_inventory_type_rel',
        'category_id', 'inventory_type_id',
        string="Inventory Types",
        help="The inventory types a product in this category may take. "
             "Leave empty to allow all of them.",
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
