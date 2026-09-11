from odoo import _, api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_resync_serial_counter(self):
        """Answer for the variant as well as the template.

        ``_inherits`` delegates the template's fields to the variant but not its
        methods, so anything that reaches a product.product -- a server action, an
        automation, an RPC call, a view we have not thought of -- would otherwise
        fail with "the method does not exist". The serial counter belongs to the
        template and a coded product has exactly one variant, so forwarding is
        unambiguous.
        """
        return self.product_tmpl_id.action_resync_serial_counter()

    def action_backfill_serial_prefix(self):
        """See action_resync_serial_counter."""
        return self.product_tmpl_id.action_backfill_serial_prefix()

    @api.onchange('tracking')
    def _onchange_tracking(self):
        """Warn before a product leaves serial or lot tracking with numbered stock.

        Core warns only in the other direction (untracked stock becoming tracked).
        This direction is the quieter one: the numbers stay on the stock but drop
        out of sight, deliveries keep taking specific serials without saying
        which, new receipts arrive unnumbered and so unbatched, and switching
        back later blocks deliveries of the unnumbered units.

        A warning rather than a block, deliberately. Raw materials flipped to
        serial by the item code generator (before that was fixed) hold exactly
        this kind of stock and need exactly this change, so refusing it would
        stop the cleanup the warning exists to make safe.

        Lives on the variant because core's template onchange delegates here,
        which puts the warning on both forms. Only stock on hand counts: serials
        that have all left the building are history and survive the change.
        """
        result = super()._onchange_tracking()
        if result:
            return result
        leaving = self.filtered(
            lambda product: product.tracking == 'none'
            and product._origin.tracking in ('lot', 'serial')
        )
        if not leaving._origin:
            return None
        [(quantity, lots)] = self.env['stock.quant'].sudo()._read_group(
            [
                ('product_id', 'in', leaving._origin.ids),
                ('lot_id', '!=', False),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
            ],
            aggregates=['quantity:sum', 'lot_id:count_distinct'],
        )
        if not lots:
            return None
        return {'warning': {
            'title': _("Serial numbers in stock"),
            'message': _(
                "%(quantity)s units of this product are in stock under "
                "%(lots)s serial/lot numbers. Switching to By Quantity hides "
                "those numbers: deliveries will still take specific serials "
                "without showing which, and new receipts will arrive with no "
                "serial number, batch or warranty date. Switching back later "
                "will block deliveries until the unnumbered units are given "
                "serials through an inventory adjustment. For goods that "
                "should never have been serialised, such as raw materials, "
                "this is fine.",
                quantity='%g' % quantity,
                lots=lots,
            ),
        }}
