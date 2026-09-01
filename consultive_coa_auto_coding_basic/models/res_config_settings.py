from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    caac_serial_width = fields.Integer(
        related='company_id.caac_serial_width',
        string="Account Code Serial Width",
        readonly=False,
    )
    caac_enforce_auto = fields.Boolean(
        related='company_id.caac_enforce_auto',
        string="Enforce Automatic Account Coding",
        readonly=False,
    )
