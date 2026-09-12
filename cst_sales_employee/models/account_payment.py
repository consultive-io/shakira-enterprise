from odoo import models, fields

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    sales_employee_id = fields.Many2one(
        'hr.employee', 
        string='Sales Employee',
        tracking=True
    )
