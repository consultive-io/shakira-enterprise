from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    sales_employee_id = fields.Many2one(
        'hr.employee', 
        string='Sales Employee',
        compute='_compute_sales_employee_id',
        store=True,
        readonly=False,
        precompute=True,
        copy=True,
        tracking=True
    )

    @api.depends('partner_id')
    def _compute_sales_employee_id(self):
        for move in self:
            if not move.sales_employee_id and move.partner_id.sales_employee_id:
                move.sales_employee_id = move.partner_id.sales_employee_id
    
    def _reverse_move_vals(self, default_values, cancel=True):
        vals = super()._reverse_move_vals(default_values, cancel=cancel)
        if self.sales_employee_id:
            vals['sales_employee_id'] = self.sales_employee_id.id
        return vals


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    sales_employee_id = fields.Many2one(
        'hr.employee',
        string='Sales Employee',
        related='move_id.sales_employee_id',
        store=True,
        readonly=False,
        copy=True
    )

