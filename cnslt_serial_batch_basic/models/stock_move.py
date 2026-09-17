from odoo import _, api, models
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def action_generate_lot_line_vals(self, context_data, mode, first_lot, count, lot_text):
        """Refuse to generate from a blank First SN.

        Left blank, core numbers from nothing: generate_lot_names('') yields
        "0", "1", "2", serials outside the product's series and outside its
        counter, which then collide with the real ones and leave units carrying
        numbers no report can trace.

        Blank is the normal state of that box since it was made read-only -- New
        is what fills it -- so this is the one mistake the dialog invites, and it
        has to be refused rather than corrected silently: the first number has to
        come from the counter, and only New draws it.

        ``@api.model`` has to be kept, as core and product_expiry keep it:
        without it call_kw reads the first RPC argument as the record ids, so
        every argument shifts by one -- the dialog's context is swallowed as
        "ids" and the mode arrives where the context belongs. The dialog then
        fails before reaching this check.
        """
        if mode == 'generate' and not (first_lot or '').strip():
            raise UserError(_(
                "Click New to draw the first serial number before generating. "
                "Serial numbers have to come from this product's own counter, so "
                "the first one cannot be left blank."
            ))
        return super().action_generate_lot_line_vals(context_data, mode, first_lot, count, lot_text)

    def _missing_serial_count(self):
        """Units on this line still waiting for a serial number.

        Counted against the demand -- the quantity the receipt is for -- less
        whatever already carries a number, so a line numbered by hand or by an
        earlier click is topped up rather than numbered twice.
        """
        self.ensure_one()
        if self.has_tracking != 'serial' or self.state in ('draft', 'done', 'cancel'):
            return 0
        numbered = self.move_line_ids.filtered(lambda line: line.lot_id or line.lot_name)
        return max(int(self.product_qty) - int(sum(numbered.mapped('quantity_product_uom'))), 0)

    def _assign_serials_from_counter(self):
        """Give every unit still missing one a serial from the product's counter.

        The line handling is core's own (_generate_serial_move_line_commands):
        it writes names onto the lines that have none yet and creates lines
        for the rest, with putaway applied. Only the names are ours -- drawn one
        by one so the counter moves with them.
        """
        for move in self:
            missing = move._missing_serial_count()
            if not missing:
                continue
            names = move.product_id.product_tmpl_id._draw_serial_numbers(missing)
            field_data = [{'lot_name': name, 'quantity': 1} for name in names]
            if move._can_create_lot():
                move._create_lot_ids_from_move_line_vals(
                    field_data, move.product_id.id, move.company_id.id,
                )
            move.move_line_ids = move._generate_serial_move_line_commands(field_data)
            # Core reuses unnumbered lines but never removes spare ones. Any left
            # would carry quantity with no serial and push the line past its
            # demand, which validation then refuses.
            move.move_line_ids.filtered(lambda line: not line.lot_id and not line.lot_name).unlink()
