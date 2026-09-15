from odoo import fields, models


class ResBank(models.Model):
    _inherit = 'res.bank'

    branch_ids = fields.Many2many('res.bank.branch', string="Branches")
