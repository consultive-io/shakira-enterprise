from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

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
        for order in self:
            if not order.sales_employee_id and order.partner_id.sales_employee_id:
                order.sales_employee_id = order.partner_id.sales_employee_id

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.sales_employee_id:
            invoice_vals['sales_employee_id'] = self.sales_employee_id.id
        return invoice_vals
