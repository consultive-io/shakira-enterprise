from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .partner_code_segment_mixin import strip_code_prefix

SEQUENCE_MAX = 999999
SEQUENCE_PADDING = 6
SEQUENCE_CODE_PREFIX = 'partner.code.'

# Changing either of these reissues the code, so a contact never carries one that
# no longer describes its classification.
SOURCE_FIELDS = ('partner_type_id', 'partner_sub_type_id')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # The sequence is drawn per code prefix, so prefix + number can only ever
    # belong to one contact. The index makes that a database guarantee rather
    # than a property of the drawing code.
    _partner_code_uniq = models.UniqueIndex(
        "(partner_code) WHERE partner_code IS NOT NULL",
        "The Partner Code must be unique.",
    )

    # required marks the field on every form that shows it, which is what makes
    # a person classify a contact they are filling in by hand. It is only a form
    # rule: Odoo enforces required through a NOT NULL column, and res_partner
    # already holds rows without a type -- base creates the main partner and the
    # default users' contacts long before this module installs -- so the column
    # stays nullable and the flows Odoo drives itself keep working. The real
    # enforcement is _check_classification_complete below.
    partner_type_id = fields.Many2one(
        'partner.type', string="Partner Type", index='btree_not_null', tracking=True,
        required=True, help="First segment of the partner code.",
    )
    partner_sub_type_id = fields.Many2one(
        'partner.sub.type', string="Partner Sub Type", index='btree_not_null',
        tracking=True, required=True, help="Second segment of the partner code.",
    )
    # What the Sub Type picker offers: the chosen type's sub types, and nothing
    # until a type is chosen.
    allowed_partner_sub_type_ids = fields.Many2many(
        related='partner_type_id.partner_sub_type_ids',
    )
    partner_code = fields.Char(
        string="Partner Code", readonly=True, copy=False, index='btree_not_null',
        tracking=True,
        help="Partner Type code + Partner Sub Type code + a six-digit sequence. "
             "The type and sub type codes are up to four letters each, so the "
             "code is as long as they make it.",
    )

    # -- display name -------------------------------------------------------

    # Core searches a typed value against these. partner_code joins them so the
    # code alone finds the contact, which is what makes the code usable as the
    # thing people quote. The rest mirror base; keep them in step with core.
    _rec_names_search = [
        'complete_name', 'email', 'ref', 'vat', 'company_registry', 'partner_code',
    ]

    @api.depends('partner_code')
    def _compute_display_name(self):
        """Put the code in front of the name, as the segments already do.

        Decorates whatever core produced rather than rebuilding it: the base
        name depends on the commercial partner and on several context keys
        (show_address, show_email, show_vat, formatted_display_name), and all of
        that keeps working untouched.

        The depends here is additive -- Odoo collects them from every
        implementation of a compute across the MRO -- so core's stay in force
        and the name still follows a rename or an email change.

        An uncoded contact reads exactly as it did before.
        """
        super()._compute_display_name()
        for partner in self:
            if partner.partner_code:
                partner.display_name = f"[{partner.partner_code}] {partner.display_name}"

    @api.model
    def _search_display_name(self, operator, value):
        """Accept the bracketed form this display name produces.

        An export writes display_name, so without this a contact list exported
        from Odoo could not be imported again -- the same trap the segment
        models have.
        """
        return super()._search_display_name(operator, strip_code_prefix(value))

    # -- classification -----------------------------------------------------

    @api.onchange('partner_type_id')
    def _onchange_partner_type_id(self):
        """Drop a sub type the newly chosen type does not allow.

        The picker's domain only filters what can be chosen next; without this, a
        sub type picked under the previous type would survive the switch.
        """
        if self.partner_sub_type_id not in self.partner_type_id.partner_sub_type_ids:
            self.partner_sub_type_id = False

    @api.constrains('partner_type_id', 'partner_sub_type_id')
    def _check_classification(self):
        """The two rules a classification has to satisfy, in order.

        Both segments or neither. Neither is a contact nobody has classified
        yet: legal, and simply uncoded until someone assigns a type. One on its
        own is a half-filled form, and there is no code that can be built from
        it, so it is refused rather than saved and quietly left without one.

        And the pair has to be one the configuration allows. The Sub Type
        picker's domain narrows the choice in a form, but a domain is
        client-side: an ORM write, a CSV import and the API never see it and
        arrive here instead. Without this a code could assert a classification
        that does not exist, such as CUSBNK for a Customer that allows only
        Retail.
        """
        for partner in self:
            partner_type = partner.partner_type_id
            sub_type = partner.partner_sub_type_id
            if bool(partner_type) != bool(sub_type):
                raise ValidationError(_(
                    "%(missing)s is not set for \"%(partner)s\". A partner code is the "
                    "type code, the sub type code and a sequence, so a contact carries "
                    "both segments or neither.",
                    missing=_("Partner Sub Type") if partner_type else _("Partner Type"),
                    partner=partner.display_name or _("this contact"),
                ))
            # Completeness is settled above, so a sub type here always has a type
            # beside it and the message can never name an empty one.
            if sub_type and sub_type not in partner_type.partner_sub_type_ids:
                raise ValidationError(_(
                    "Partner Sub Type \"%(sub_type)s\" is not allowed under Partner "
                    "Type \"%(type)s\".",
                    sub_type=sub_type.display_name,
                    type=partner_type.display_name,
                ))

    @api.model
    def _resolve_classification(self, vals):
        """Classify a contact Odoo is creating by itself.

        Only the two situations where nobody is present to choose: the contact
        behind a new ``res.users``, and an employee's work contact. Those always
        take the pair designated for Users and for Employees respectively.

        Every other contact is left exactly as the caller asked, so one nobody
        classified stays blank rather than being pushed into a catch-all, and
        picks up a code when someone assigns a type to it.
        """
        designation = self.env.context.get('partner_code_designation')
        if not designation or vals.get('partner_type_id') or vals.get('partner_sub_type_id'):
            return vals

        # A configuration read, so sudo rather than the acting user: which pair
        # was nominated is the same answer whoever is creating the record.
        domain = [('auto_assign_to', '=', designation)]
        partner_type = self.env['partner.type'].sudo().search(domain, limit=1)
        sub_type = self.env['partner.sub.type'].sudo().search(domain, limit=1)
        # Nothing nominated: leave the contact blank rather than refusing it.
        # Raising here would make a user or an employee impossible to create,
        # which is worse than a contact that has to be classified by hand.
        if partner_type and sub_type:
            vals['partner_type_id'] = partner_type.id
            vals['partner_sub_type_id'] = sub_type.id
        return vals

    # -- generation ---------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create([self._resolve_classification(dict(v)) for v in vals_list])
        for partner in partners:
            if partner.partner_type_id:
                partner._generate_partner_code()
        return partners

    def _generate_partner_code(self):
        self.ensure_one()
        if not self.partner_type_id:
            raise ValidationError(_(
                "\"%(partner)s\" has no Partner Type, so no code can be built for "
                "it. Classify the contact first.",
                partner=self.display_name or _("this contact"),
            ))
        prefix = self.partner_type_id.code + self.partner_sub_type_id.code
        self.write({'partner_code': prefix + self._draw_sequence(prefix)})

    @api.model
    def _draw_sequence(self, prefix):
        """Draw the next number for a code prefix.

        Keyed on the prefix itself rather than on the type and sub type ids.
        Segment codes vary in length, so two different pairs can spell the same
        prefix -- type ``AB`` with sub type ``CD`` reads the same as type ``ABC``
        with sub type ``D``. Sharing one counter is what keeps prefix + number
        unique in that case; in every other case the prefix is the pair, so this
        is a per type and sub type sequence.
        """
        code = SEQUENCE_CODE_PREFIX + prefix
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([('code', '=', code)], limit=1)
        if not sequence:
            sequence = Sequence.create({
                'name': _("Partner Code - %s", prefix),
                'code': code,
                # no_gap takes a row lock, which serialises concurrent draws and
                # is what makes the ceiling reliable.
                'implementation': 'no_gap',
                'padding': SEQUENCE_PADDING,
                'company_id': False,
            })
        value = sequence.next_by_id()
        if int(value) > SEQUENCE_MAX:
            raise UserError(_(
                "The partner code sequence for %(prefix)s is exhausted: all "
                "%(maximum)s numbers have been issued. A new Partner Type or Sub "
                "Type is needed for further contacts.",
                prefix=prefix,
                maximum=SEQUENCE_MAX,
            ))
        return value

    # -- reclassification ---------------------------------------------------

    def write(self, vals):
        reclassified = self.browse()
        if any(name in vals for name in SOURCE_FIELDS) \
                and not self.env.context.get('allow_partner_code_source_change'):
            reclassified = self.filtered(lambda partner: any(
                partner[name].id != vals[name] for name in SOURCE_FIELDS if name in vals
            ))
        result = super().write(vals)
        # Issues the first code for a contact classified by hand, and reissues
        # one whose classification changed. A reissue draws a fresh number, so
        # the superseded code is never handed to another contact; it may already
        # be printed on an invoice, which is why both values are tracked.
        #
        # Clearing the classification leaves the code in place rather than
        # blanking it: it has been issued and quoted elsewhere already, so
        # withdrawing it would orphan those references.
        for partner in reclassified:
            if partner.partner_type_id:
                partner._generate_partner_code()
        return result

    def action_generate_partner_code(self):
        """Issue or reissue codes from the current classification.

        Covers the contacts that predate this module, and corrections.
        """
        if not self.env.user.has_group('base.group_partner_manager'):
            raise AccessError(_(
                "Only Contact Creation managers may generate partner codes."
            ))
        for partner in self:
            partner._generate_partner_code()
