from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    return_lot_ids = fields.Many2many(
        'stock.lot', compute='_compute_return_lot_ids',
        help="Serials of the original transfer that were not returned yet. "
             "Empty when the line does not belong to a return.",
    )

    @api.depends('move_id.origin_returned_move_id')
    def _compute_return_lot_ids(self):
        for line in self:
            origin = line.move_id.origin_returned_move_id
            others = origin.returned_move_ids.filtered(
                lambda m: m.state == 'done' and m != line.move_id)
            line.return_lot_ids = origin.move_line_ids.lot_id - others.move_line_ids.lot_id

    @api.constrains('lot_id')
    def _check_return_lot(self):
        for line in self.filtered(lambda l: l.lot_id and l.move_id.origin_returned_move_id):
            if line.lot_id not in line.return_lot_ids:
                raise ValidationError(_(
                    "Serial '%s' was not part of the original transfer or was already returned.",
                    line.lot_id.name))
