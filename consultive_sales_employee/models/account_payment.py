from odoo import models, fields, api

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    sales_employee_id = fields.Many2one(
        'hr.employee', 
        string='Sales Employee',
        compute='_compute_sales_employee_id',
        store=True,
        readonly=False,
        precompute=True,
        tracking=True
    )

    @api.depends('partner_id')
    def _compute_sales_employee_id(self):
        for payment in self:
            if not payment.sales_employee_id and payment.partner_id.sales_employee_id:
                payment.sales_employee_id = payment.partner_id.sales_employee_id
