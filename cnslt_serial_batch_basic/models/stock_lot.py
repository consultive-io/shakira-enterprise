from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockLot(models.Model):
    _inherit = 'stock.lot'

    batch_id = fields.Many2one(
        'inventory.serial.batch', string="Batch",
        ondelete='restrict', index=True, copy=False,
        help="The receipt or manufacturing run this unit came from.",
    )
    # Stored rather than a plain related: warranty reports filter and sort on it,
    # and a non-stored related cannot be searched.
    warranty_end_date = fields.Date(
        related='batch_id.warranty_end_date', store=True, index=True,
    )

    @api.constrains('batch_id', 'product_id')
    def _check_batch_product(self):
        """A serial may only join a batch for its own product.

        This lives on the lot rather than only on the batch because it is the lot
        that gets written: the receipt and manufacturing hooks attach serials by
        setting ``batch_id`` on them, and a ``constrains('lot_ids')`` on the batch
        fires only when the one2many is written through the batch itself.

        What it protects is not cosmetic. ``warranty_end_date`` above is a *stored*
        related reaching through ``batch_id``, so a lot placed in the wrong batch
        silently takes on another product's warranty terms and arrival date, in a
        stored, indexed column that warranty reports then read as fact.
        """
        for lot in self:
            batch = lot.batch_id
            if batch and batch.product_id != lot.product_id:
                raise ValidationError(_(
                    "Serial number \"%(lot)s\" is for %(lot_product)s, but batch "
                    "\"%(batch)s\" is for %(batch_product)s. A batch holds serials "
                    "of one product only: its date and warranty describe those "
                    "goods and would be wrong for anything else.",
                    lot=lot.name,
                    lot_product=lot.product_id.display_name,
                    batch=batch.name,
                    batch_product=batch.product_id.display_name,
                ))
