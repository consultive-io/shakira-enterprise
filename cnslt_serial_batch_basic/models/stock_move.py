from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _default_picking_has_purchase_id(self):
        picking_id = self.env.context.get('default_picking_id') or self.env.context.get('active_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            return bool(getattr(picking, 'purchase_id', False))
        return False

    picking_has_purchase_id = fields.Boolean(
        string="Receipt Has Purchase Order",
        compute='_compute_picking_has_purchase_id',
        default=_default_picking_has_purchase_id,
    )

    @api.depends('picking_id.purchase_id', 'purchase_line_id')
    def _compute_picking_has_purchase_id(self):
        for move in self:
            picking = move.picking_id
            if not picking:
                picking_id = self.env.context.get('default_picking_id') or self.env.context.get('active_picking_id')
                if picking_id:
                    picking = self.env['stock.picking'].browse(picking_id)
            has_po = bool(picking and getattr(picking, 'purchase_id', False))
            if not has_po:
                has_po = bool(getattr(move, 'purchase_line_id', False))
            move.picking_has_purchase_id = has_po

    @api.onchange('picking_id', 'purchase_line_id')
    def _onchange_picking_for_purchase(self):
        self._compute_picking_has_purchase_id()

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
