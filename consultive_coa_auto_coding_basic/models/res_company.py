from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    caac_serial_width = fields.Integer(
        string="Account Code Serial Width",
        default=3,
        help="Default number of trailing digits reserved for the running serial when "
             "generating account codes. Can be overridden per account group.",
    )
    caac_enforce_auto = fields.Boolean(
        string="Enforce Automatic Account Coding",
        default=False,
        help="When enabled, the coding mode is locked to Automatic on the account form "
             "and a coding group must be selected.",
    )
