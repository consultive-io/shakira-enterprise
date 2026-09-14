from odoo import models

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        moves = self.line_ids.move_id
        sales_employees = moves.mapped('sales_employee_id')
        if len(sales_employees) == 1 and sales_employees:
            payment_vals['sales_employee_id'] = sales_employees[0].id
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        moves = batch_result['lines'].move_id
        sales_employees = moves.mapped('sales_employee_id')
        if len(sales_employees) == 1 and sales_employees:
            payment_vals['sales_employee_id'] = sales_employees[0].id
        return payment_vals
