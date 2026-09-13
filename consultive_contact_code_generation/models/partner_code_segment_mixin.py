import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Alphabetic only and at most four characters. Digits are excluded on purpose:
# the sequence is the only numeric part of a partner code, so a digit in a
# segment would make the boundary between prefix and sequence unreadable.
CODE_PATTERN = re.compile(r'^[A-Z]+$')
CODE_MAX_LENGTH = 4

# The "[CUS] " that display_name puts in front of a name, which an export writes
# back out and an import has to be able to read again. Digits are allowed so the
# same helper strips a contact's "[CUSRTL000001] " as well as a segment's "[CUS] ".
CODE_PREFIX_PATTERN = re.compile(r'^\[[A-Za-z0-9]*\]\s*')


def strip_code_prefix(value):
    """Drop a leading "[CUS] " from a search value, whatever shape it arrives in.

    The ORM normalises ``=`` into ``in`` and hands the value over as a set, so a
    plain string check is not enough -- it would silently skip every equality
    search, which is exactly the form an import uses.
    """
    if isinstance(value, str):
        return CODE_PREFIX_PATTERN.sub('', value, count=1) or value
    if hasattr(value, '__iter__'):
        return [strip_code_prefix(item) for item in value]
    return value


# The two slots a segment can be designated for. Odoo creates a contact on its
# own in both situations -- behind a new user, and behind a new employee -- with
# nobody present to classify it, so each needs a segment nominated ahead of time.
DESIGNATIONS = [
    ('user', "Users"),
    ('employee', "Employees"),
]


class PartnerCodeSegmentMixin(models.AbstractModel):
    """Shared behaviour for the segments that make up a partner code.

    Carries the name and code, the code's format rule, uppercase normalisation,
    the designation that nominates a segment for contacts Odoo creates by
    itself, and the guard that stops a code changing once partner codes have
    been issued from it.
    """
    _name = 'partner.code.segment.mixin'
    _description = "Partner Code Segment"
    _order = 'code'

    name = fields.Char(required=True)
    code = fields.Char(
        required=True, index=True, copy=False,
        help="Segment used to assemble the partner code. Letters only, at most "
             "%s characters." % CODE_MAX_LENGTH,
    )
    active = fields.Boolean(default=True)
    auto_assign_to = fields.Selection(
        DESIGNATIONS, string="Assigned Automatically To", copy=False, index=True,
        help="Nominates this record for the contacts Odoo creates without "
             "anyone choosing a classification: the contact behind a new user, "
             "and an employee's work contact. Only one record may hold each "
             "designation.",
    )

    # Matching a typed or imported value against the code as well as the name,
    # so a data file can identify a segment by either.
    _rec_names_search = ['name', 'code']

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.code}] {record.name}" if record.code else record.name

    @api.model
    def _search_display_name(self, operator, value):
        """Also accept the bracketed form that display_name produces.

        Exporting a many2one writes its display_name, "[CUS] Customer". Without
        this, that value cannot be imported again -- the brackets match neither
        the name nor the code -- so an export could not be edited and reloaded,
        which is the ordinary way bulk data gets fixed up.
        """
        return super()._search_display_name(operator, strip_code_prefix(value))

    # -- code format --------------------------------------------------------

    @api.constrains('code')
    def _check_code_format(self):
        for record in self:
            if not record.code:
                continue
            if not CODE_PATTERN.match(record.code):
                raise ValidationError(_(
                    "Code \"%(code)s\" is not valid: it may only contain letters "
                    "-- no digits, spaces or punctuation.",
                    code=record.code,
                ))
            if len(record.code) > CODE_MAX_LENGTH:
                raise ValidationError(_(
                    "Code \"%(code)s\" is not valid: it may be at most "
                    "%(length)s characters, and it is %(actual)s.",
                    code=record.code,
                    length=CODE_MAX_LENGTH,
                    actual=len(record.code),
                ))

    @api.model
    def _normalise_vals(self, vals):
        """Uppercase the code, and store an unset code or designation as NULL.

        Postgres allows many NULLs under a unique constraint but treats the
        empty string as a real value, so two blank codes -- or two segments
        nominated for nothing -- would collide with each other.
        """
        if 'code' in vals:
            vals['code'] = (vals['code'] or '').strip().upper() or False
        if 'auto_assign_to' in vals:
            vals['auto_assign_to'] = vals['auto_assign_to'] or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._normalise_vals(dict(vals)) for vals in vals_list])

    def write(self, vals):
        vals = self._normalise_vals(dict(vals))
        if 'code' in vals:
            for record in self:
                if record.code and record.code != vals['code'] and record._code_is_in_use():
                    raise ValidationError(_(
                        "The code of \"%(name)s\" cannot be changed: partner codes "
                        "have already been issued from it. Those contacts would be "
                        "left carrying a code that no longer matches their "
                        "classification.",
                        name=record.display_name,
                    ))
        return super().write(vals)

    def _code_is_in_use(self):
        """Whether any contact has already been issued a code from this record."""
        self.ensure_one()
        return False
