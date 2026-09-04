from odoo import _, api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    serial_batch_ids = fields.One2many(
        'inventory.serial.batch', 'picking_id', string="Serial Batches",
    )
    serial_batch_count = fields.Integer(compute='_compute_serial_batch_count')

    @api.depends('serial_batch_ids')
    def _compute_serial_batch_count(self):
        counts = dict(self.env['inventory.serial.batch']._read_group(
            [('picking_id', 'in', self.ids)], ['picking_id'], ['__count'],
        ))
        for picking in self:
            picking.serial_batch_count = counts.get(picking, 0)

    def action_view_serial_batches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Serial Batches"),
            'res_model': 'inventory.serial.batch',
            'view_mode': 'list,form',
            'domain': [('picking_id', '=', self.id)],
        }

    def button_validate(self):
        """Batch the serials once the receipt has actually been validated.

        ``state == 'done'`` is checked rather than assumed: core returns a wizard
        action -- a backorder or an immediate-transfer question -- straight out of
        ``_pre_action_done_hook`` without having validated anything
        (``stock_picking.py:1437``). Confirming that wizard re-enters this method,
        and the batches are made on that second pass.
        """
        result = super().button_validate()
        self.filtered(
            lambda picking: picking.state == 'done'
            and picking.picking_type_id.code == 'incoming'
        )._create_serial_batches()
        return result

    def _create_serial_batches(self):
        """One batch per product received, carrying this receipt's date and supplier.

        A backorder is a separate picking validated on its own day, so it earns its
        own batch rather than joining this one -- which is the point, since the
        goods arrived later and their warranty runs from then.
        """
        Batch = self.env['inventory.serial.batch']
        for picking in self:
            lots = picking.move_line_ids.lot_id
            if not lots:
                continue
            Batch._create_serial_batches(
                lots,
                source_type='receipt',
                document=picking,
                # date_done is a Datetime; read it as a date in the user's
                # timezone so an evening receipt is not booked to tomorrow.
                date=fields.Date.context_today(picking, picking.date_done),
                partner=picking.partner_id,
            )
