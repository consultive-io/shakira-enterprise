from odoo import fields, models


class ResBankBranch(models.Model):
    _name = 'res.bank.branch'
    _description = "Bank Branch"
    _order = 'name'

    name = fields.Char(required=True)
    route = fields.Char(string="Routing Number")
