from odoo import models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _create_work_contacts(self):
        """Classify the work contact Odoo creates behind a new employee.

        Overridden at the point the contact is created rather than in ``create``,
        which covers both callers: creating an employee, and filling in work
        details on an employee that has no work contact yet.

        An employee linked to a user takes that user's contact as its work
        contact instead of creating one, so it keeps the code already issued
        under the Users designation.
        """
        return super(
            HrEmployee, self.with_context(partner_code_designation='employee')
        )._create_work_contacts()
