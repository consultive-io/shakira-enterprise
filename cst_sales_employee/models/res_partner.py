from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    sales_employee_id = fields.Many2one(
        'hr.employee', 
        string='Sales Employee',
        help='Sales Employee in charge of this customer.'
    )
