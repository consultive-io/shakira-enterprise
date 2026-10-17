from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _default_picking_has_purchase_id(self):
        picking_id = self.env.context.get('default_picking_id') or self.env.context.get('active_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            return bool(getattr(picking, 'purchase_id', False))
        move_id = self.env.context.get('default_move_id')
        if move_id:
            move = self.env['stock.move'].browse(move_id)
            return bool(getattr(move, 'purchase_line_id', False) or getattr(move.picking_id, 'purchase_id', False))
        return False

    picking_has_purchase_id = fields.Boolean(
        string="Receipt Has Purchase Order",
        compute='_compute_picking_has_purchase_id',
        default=_default_picking_has_purchase_id,
    )

    @api.depends('picking_id.purchase_id', 'move_id.picking_id.purchase_id', 'move_id.purchase_line_id')
    def _compute_picking_has_purchase_id(self):
        for line in self:
            picking = line.picking_id or line.move_id.picking_id
            if not picking:
                picking_id = self.env.context.get('default_picking_id') or self.env.context.get('active_picking_id')
                if picking_id:
                    picking = self.env['stock.picking'].browse(picking_id)
            has_po = bool(picking and getattr(picking, 'purchase_id', False))
            if not has_po and line.move_id:
                has_po = bool(getattr(line.move_id, 'purchase_line_id', False))
            line.picking_has_purchase_id = has_po

    @api.onchange('picking_id', 'move_id')
    def _onchange_picking_for_purchase(self):
        self._compute_picking_has_purchase_id()
