import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# The Internal Reference is 7 characters and the specified serial number is 13, so
# the counter gets the remaining 6.
SERIAL_PADDING = 6

# The code Odoo gives the sequences it creates from serial_prefix_format. Used to
# tell those apart from a sequence somebody configured by hand.
LOT_SEQUENCE_CODE = 'stock.lot.serial'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    default_warranty_months = fields.Integer(
        string="Warranty (Months)", default=0,
        help="Copied onto each batch as it is created. Changing it here affects "
             "future batches only, so units already sold keep the terms they "
             "were sold under.",
    )
    # next_serial shows what the counter claims comes next; these show what was
    # actually issued, which is the only thing that can collide.
    last_serial_used = fields.Char(
        compute='_compute_serial_counter_state',
        help="The highest serial number issued for this product so far.",
    )
    serial_counter_drift = fields.Boolean(compute='_compute_serial_counter_state')
    serial_counter_message = fields.Char(compute='_compute_serial_counter_state')

    @api.constrains('default_warranty_months')
    def _check_default_warranty_months(self):
        for template in self:
            if template.default_warranty_months < 0:
                raise ValidationError(_(
                    "The warranty on \"%(product)s\" cannot be negative.",
                    product=template.display_name,
                ))

    # -- the prefix ---------------------------------------------------------

    def _serial_prefix(self):
        """The string every serial number for this product starts with.

        The Internal Reference, which the item code generator issues and the
        database guarantees to be unique. Uniqueness matters here rather than just
        being tidy: Odoo picks a product's serial sequence by matching the prefix
        string, so two products sharing a prefix would share one counter.

        This is also the seam for per-variant codes. When
        ``_item_code_supports_variants`` is turned on, the prefix comes from the
        variant rather than the product, and ``lot_sequence_id`` has to move with
        it -- everything else in this module reads the prefix from here.
        """
        self.ensure_one()
        return self.default_code or ''

    def _serial_sequence_is_ours(self, sequence):
        """Whether this module is responsible for the given sequence.

        Deliberately narrow. Odoo reuses an existing sequence whenever the prefix
        matches, so a product can end up pointing at one an administrator built for
        their own purposes, and rewriting that would change how a completely
        different product numbers its stock.
        """
        self.ensure_one()
        prefix = self._serial_prefix()
        # An empty prefix can never identify a sequence of ours. A product without
        # a code sits on Odoo's shared default sequence, whose prefix is empty too,
        # so matching empty against empty would claim the sequence every product in
        # the database falls back to.
        if not sequence or not prefix:
            return False
        return sequence.code == LOT_SEQUENCE_CODE and sequence.prefix == prefix

    # -- assignment ---------------------------------------------------------

    def _generate_item_code(self):
        """Give the product its serial sequence in the same breath as its code.

        Extending generation rather than adding another ``create`` override keeps
        this atomic: there is never a moment when a coded product exists without the
        sequence that a receipt or a manufacturing order is about to need, and the
        backfill below is only ever needed for products that predate this module.
        """
        super()._generate_item_code()
        prefix = self._serial_prefix()
        if not prefix:
            return
        values = {'serial_prefix_format': prefix}
        # Coded goods are tracked by default, but only where Odoo allows it:
        # _compute_tracking forces 'none' back onto anything not storable, so
        # setting it there would be silently undone.
        if self.is_storable and self.tracking == 'none':
            values['tracking'] = 'serial'
        self.with_context(allow_item_code_source_change=True).write(values)

    def _inverse_serial_prefix_format(self):
        """Odoo builds the sequence with padding 7; ours needs 6.

        Left alone, a 7-character Internal Reference and a 7-digit counter would
        produce a 14-character serial number, one over the specification.
        """
        super()._inverse_serial_prefix_format()
        for template in self:
            template._align_serial_sequence()

    def _align_serial_sequence(self):
        """Force our padding onto a sequence this module caused to exist."""
        self.ensure_one()
        sequence = self.lot_sequence_id
        if not self._serial_sequence_is_ours(sequence):
            return
        if sequence.padding != SERIAL_PADDING:
            sequence.sudo().padding = SERIAL_PADDING

    # -- what was actually issued -------------------------------------------

    def _highest_issued_serial(self):
        """The furthest this product's numbering has actually reached.

        Returns ``(lot, number)``, or an empty lot and 0 when nothing matches.

        Deliberately the *highest* rather than the most recently created. The two
        agree on a well-behaved product and diverge exactly when something has
        gone wrong, and it is the highest that decides whether the next draw
        collides.

        Lots that do not fit the product's prefix are skipped rather than treated
        as an error. Hand-entered and migrated serials live there, and they are
        the very case this is used to investigate -- raising on them would break
        the tool precisely when it is needed.
        """
        self.ensure_one()
        Lot = self.env['stock.lot']
        prefix = self._serial_prefix()
        if not prefix:
            return Lot.browse(), 0

        highest_lot, highest_number = Lot.browse(), 0
        lots = Lot.sudo().search([('product_id', 'in', self.product_variant_ids.ids)])
        for lot in lots:
            name = lot.name or ''
            if not name.startswith(prefix):
                continue
            tail = name[len(prefix):]
            if not tail.isdigit():
                continue
            number = int(tail)
            if number > highest_number:
                highest_lot, highest_number = lot, number
        return highest_lot, highest_number

    @api.depends('lot_sequence_id', 'lot_sequence_id.number_next_actual')
    def _compute_serial_counter_state(self):
        """Last issued, and whether the counter has fallen behind it."""
        for template in self:
            _lot, highest = template._highest_issued_serial()
            sequence = template.lot_sequence_id
            prefix = template._serial_prefix()

            template.last_serial_used = (
                '%s%0*d' % (prefix, SERIAL_PADDING, highest) if highest else False
            )

            # Only the counter falling *behind* matters. Running ahead leaves
            # gaps -- a discarded "New", a deleted lot -- which are untidy but
            # harmless, and flagging them would cry wolf on ordinary use.
            behind = bool(
                highest
                and template._serial_sequence_is_ours(sequence)
                and sequence.number_next_actual <= highest
            )
            template.serial_counter_drift = behind
            template.serial_counter_message = _(
                "The next serial number this product would issue (%(next)s) has "
                "already been used. The counter is behind the serials on record, "
                "so the next receipt will be refused as a duplicate. Resync the "
                "counter to continue from %(resume)s.",
                next=sequence.get_next_char(sequence.number_next_actual),
                resume='%s%0*d' % (prefix, SERIAL_PADDING, highest + 1),
            ) if behind else False

    def action_resync_serial_counter(self):
        """Move the counter past the highest serial already issued.

        The alternative is editing the ``ir.sequence`` by hand in Technical
        settings, which needs developer mode, the right record among hundreds,
        and the correct number worked out from the lot list -- and leaves no
        trace afterwards. This does it in one click and posts to the chatter.
        """
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_(
                "Only Inventory Managers may resync serial number counters."
            ))

        resynced = self.browse()
        for template in self:
            sequence = template.lot_sequence_id
            # Never touch a sequence this module did not cause to exist: it may
            # be numbering somebody else's stock.
            if not template._serial_sequence_is_ours(sequence):
                continue
            _lot, highest = template._highest_issued_serial()
            if not highest:
                continue
            target = highest + 1
            previous = sequence.number_next_actual
            if previous == target:
                continue
            sequence.sudo().number_next_actual = target
            template.message_post(body=_(
                "Serial number counter resynced from %(previous)s to %(target)s, "
                "past the highest serial issued (%(highest)s).",
                previous=previous,
                target=target,
                highest=template.last_serial_used,
            ))
            resynced |= template
        return len(resynced)

    # -- regeneration -------------------------------------------------------

    def _issued_serial_count(self):
        """How many serial numbers have been issued for this product."""
        self.ensure_one()
        return self.env['stock.lot'].sudo().search_count([
            ('product_id', 'in', self.product_variant_ids.ids),
        ])

    def action_regenerate_item_code(self):
        """Refuse to reissue a code once serial numbers exist under the old one.

        Regeneration draws a new Internal Reference and the serial prefix follows
        it, so the product starts issuing ``ZIZT002...`` while every unit already
        built carries ``ZIZT001...`` on its rating plate. Those plates cannot be
        changed, nothing records that the two families are the same product, and
        the new counter restarts at 1.

        Checked for the whole recordset before regenerating any of it, so a mixed
        selection fails cleanly instead of half-applying. Enforced here rather
        than by hiding the button: the damage is permanent and a hidden button is
        still reachable from a list action or RPC.
        """
        for template in self:
            issued = template._issued_serial_count()
            if issued:
                raise UserError(_(
                    "\"%(product)s\" cannot be given a new item code: %(count)s "
                    "serial numbers have already been issued from %(code)s, and "
                    "they are printed on units that have shipped. A new code "
                    "would leave those units carrying a reference this product no "
                    "longer has.\n\n"
                    "Changing the code at this point is a data migration, not a "
                    "button. Archive this product and create a replacement under "
                    "the correct classification instead.",
                    product=template.display_name,
                    count=issued,
                    code=template.default_code or _("its current code"),
                ))
        return super().action_regenerate_item_code()

    # -- backfill -----------------------------------------------------------

    def _serial_prefix_backfill_domain(self):
        """Coded products still sitting on Odoo's shared lot sequence.

        ``serial_prefix_format`` is computed and not stored, so it cannot be
        searched; what it reflects is ``lot_sequence_id``, which *is* a column.
        A product that never had a prefix written points at
        ``stock.sequence_production_lots`` -- core's default for the field -- or
        at nothing at all.
        """
        domain = [('item_code', '!=', False)]
        shared = self.env.ref('stock.sequence_production_lots', raise_if_not_found=False)
        if shared:
            domain += ['|', ('lot_sequence_id', '=', False), ('lot_sequence_id', '=', shared.id)]
        else:
            domain += [('lot_sequence_id', '=', False)]
        return domain

    def action_backfill_serial_prefix(self):
        """Give already-coded products the serial prefix they never received.

        Needed only for products created after the item code generator was
        installed but before this module was: their Internal Reference exists, but
        nothing wrote ``serial_prefix_format`` at the time, so they still sit on
        Odoo's shared lot sequence and would issue serials with no prefix, shared
        with every other product in that position.

        Operates on the current selection, or on the whole catalogue when called
        on an empty recordset. Returns the number of products changed, so running
        it a second time reports that there was nothing left to do.

        It never draws a new Internal Reference: the existing code may already be
        printed on labels and purchase orders, so the prefix is taken from the
        code the product already carries.
        """
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_(
                "Only Inventory Managers may backfill serial prefixes."
            ))

        domain = self._serial_prefix_backfill_domain()
        candidates = self.filtered_domain(domain) if self else self.search(domain)

        backfilled = 0
        for template in candidates:
            prefix = template._serial_prefix()
            # Comparing rather than writing blindly keeps the run idempotent and
            # avoids touching the sequence of a product that is already correct.
            if not prefix or template.serial_prefix_format == prefix:
                continue
            template.serial_prefix_format = prefix
            backfilled += 1

        _logger.info(
            "cnslt_serial_batch_basic: backfilled the serial prefix on %s products.",
            backfilled,
        )
        return backfilled

