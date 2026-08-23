import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CODE_PATTERN = re.compile(r'^[A-Z0-9]{2}$')


class CodeSegmentMixin(models.AbstractModel):
    """Shared behaviour for the two-character codes that make up an item code.

    Carries the field, its format rule, uppercase normalisation, and the guard
    that stops a code changing once item codes have been issued from it.
    """
    _name = 'inventory.code.segment.mixin'
    _description = "Two-Character Code Segment"

    code = fields.Char(
        size=2, index=True, copy=False,
        help="Two-character segment used to assemble the item code. "
             "Uppercase letters and digits only.",
    )

    @api.constrains('code')
    def _check_code_format(self):
        for record in self:
            if record.code and not CODE_PATTERN.match(record.code):
                raise ValidationError(_(
                    "Code \"%(code)s\" is not valid: it must be exactly two "
                    "uppercase letters or digits.",
                    code=record.code,
                ))

    @api.model
    def _normalise_code(self, vals):
        """Uppercase the code, and store an empty one as NULL rather than ''.

        Postgres allows many NULLs under a unique constraint but treats the empty
        string as a real value, so two blank codes would collide with each other.
        """
        if 'code' in vals:
            code = (vals['code'] or '').strip().upper()
            vals['code'] = code or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._normalise_code(dict(vals)) for vals in vals_list])

    def write(self, vals):
        vals = self._normalise_code(dict(vals))
        if 'code' in vals:
            for record in self:
                if record.code and record.code != vals['code'] and record._code_is_in_use():
                    raise ValidationError(_(
                        "The code of \"%(name)s\" cannot be changed: item codes have "
                        "already been issued from it. Those products would be left "
                        "carrying a code that no longer matches their classification.",
                        name=record.display_name,
                    ))
        return super().write(vals)

    def _code_is_in_use(self):
        """Whether any product has already been issued an item code from this record."""
        self.ensure_one()
        return False
