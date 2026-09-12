from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    sales_employee_id = fields.Many2one(
        'hr.employee', 
        string='Sales Employee',
        copy=True,
        tracking=True
    )
    
    def _reverse_move_vals(self, default_values, cancel=True):
        vals = super()._reverse_move_vals(default_values, cancel=cancel)
        if self.sales_employee_id:
            vals['sales_employee_id'] = self.sales_employee_id.id
        return vals
