from odoo import _, api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    serial_batch_ids = fields.One2many(
        'inventory.serial.batch', 'production_id', string="Serial Batches",
    )
    serial_batch_count = fields.Integer(compute='_compute_serial_batch_count')

    @api.depends('serial_batch_ids')
    def _compute_serial_batch_count(self):
        counts = dict(self.env['inventory.serial.batch']._read_group(
            [('production_id', 'in', self.ids)], ['production_id'], ['__count'],
        ))
        for production in self:
            production.serial_batch_count = counts.get(production, 0)

    def action_view_serial_batches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Serial Batches"),
            'res_model': 'inventory.serial.batch',
            'view_mode': 'list,form',
            'domain': [('production_id', '=', self.id)],
        }

    def button_mark_done(self):
        """Batch the finished serials once the order has actually closed.

        Same reasoning as the receipt hook: ``pre_button_mark_done`` can return a
        wizard -- backorder, or a consumption warning -- without the order having
        been marked done (``mrp_production.py:2220``), so ``done`` is verified
        afterwards rather than assumed.
        """
        result = super().button_mark_done()
        self.filtered(lambda production: production.state == 'done')._create_serial_batches()
        return result

    def _create_serial_batches(self):
        """One batch per manufacturing order, holding the serials it produced.

        Only the finished good is batched. Component lots reaching
        ``finished_move_line_ids`` belong to goods made elsewhere and already carry
        a batch of their own from whenever they were received or produced.
        """
        Batch = self.env['inventory.serial.batch']
        for production in self:
            lots = production.finished_move_line_ids.filtered(
                lambda line: line.product_id == production.product_id
            ).lot_id
            if not lots:
                continue
            Batch._create_serial_batches(
                lots,
                source_type='manufacturing',
                document=production,
                date=fields.Date.context_today(production, production.date_finished),
            )
