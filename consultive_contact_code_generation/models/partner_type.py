from odoo import fields, models


class PartnerType(models.Model):
    _name = 'partner.type'
    _inherit = ['partner.code.segment.mixin']
    _description = "Partner Type"

    _code_uniq = models.Constraint(
        'unique(code)',
        "The Partner Type code must be unique.",
    )
    # A partial unique index rather than a plain unique constraint: most types
    # are nominated for nothing, and those must not collide with each other.
    _auto_assign_uniq = models.UniqueIndex(
        "(auto_assign_to) WHERE auto_assign_to IS NOT NULL",
        "Only one Partner Type may be assigned automatically to Users, and one "
        "to Employees. Clear the designation on the type that holds it before "
        "giving it to another.",
    )

    partner_sub_type_ids = fields.Many2many(
        'partner.sub.type', 'partner_type_sub_type_rel',
        'type_id', 'sub_type_id',
        string="Partner Sub Types",
        help="The sub types a contact of this type may take, and all a contact "
             "of this type is offered.",
    )

    def _code_is_in_use(self):
        self.ensure_one()
        return bool(self.env['res.partner'].sudo().search_count([
            ('partner_type_id', '=', self.id),
            ('partner_code', '!=', False),
        ], limit=1))


class PartnerSubType(models.Model):
    _name = 'partner.sub.type'
    _inherit = ['partner.code.segment.mixin']
    _description = "Partner Sub Type"

    _code_uniq = models.Constraint(
        'unique(code)',
        "The Partner Sub Type code must be unique.",
    )
    _auto_assign_uniq = models.UniqueIndex(
        "(auto_assign_to) WHERE auto_assign_to IS NOT NULL",
        "Only one Partner Sub Type may be assigned automatically to Users, and "
        "one to Employees. Clear the designation on the sub type that holds it "
        "before giving it to another.",
    )

    partner_type_ids = fields.Many2many(
        'partner.type', 'partner_type_sub_type_rel',
        'sub_type_id', 'type_id',
        string="Partner Types",
        help="The types that allow this sub type.",
    )

    def _code_is_in_use(self):
        self.ensure_one()
        return bool(self.env['res.partner'].sudo().search_count([
            ('partner_sub_type_id', '=', self.id),
            ('partner_code', '!=', False),
        ], limit=1))
