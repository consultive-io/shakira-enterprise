from odoo import api, fields, models


class InventoryCategory(models.Model):
    _name = 'inventory.category'
    _inherit = ['inventory.code.segment.mixin']
    _description = "Inventory Category"
    _order = 'code'

    _code_uniq = models.Constraint(
        'unique(code)',
        "The Inventory Category code must be unique.",
    )

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}" if record.code else record.name

    def _code_is_in_use(self):
        self.ensure_one()
        return bool(self.env['product.template'].sudo().search_count([
            ('inventory_category_id', '=', self.id),
            ('item_code', '!=', False),
        ], limit=1))


class InventoryType(models.Model):
    _name = 'inventory.type'
    _inherit = ['inventory.code.segment.mixin']
    _description = "Inventory Type"
    _order = 'code'

    _code_uniq = models.Constraint(
        'unique(code)',
        "The Inventory Type code must be unique.",
    )

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}" if record.code else record.name

    def _code_is_in_use(self):
        self.ensure_one()
        return bool(self.env['product.template'].sudo().search_count([
            ('inventory_type_id', '=', self.id),
            ('item_code', '!=', False),
        ], limit=1))
