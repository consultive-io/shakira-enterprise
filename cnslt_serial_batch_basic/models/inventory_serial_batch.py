from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

SEQUENCE_CODE = 'inventory.serial.batch'


class InventorySerialBatch(models.Model):
    """One receipt or manufacturing run of a single product.

    The serial numbers themselves carry no date, so the batch is where a unit's
    age and warranty live. One batch per (document, product) pair: a backorder or
    a split manufacturing order arrives on its own date and therefore earns its
    own batch rather than joining the original.
    """
    _name = 'inventory.serial.batch'
    _description = "Serial Number Batch"
    _order = 'date desc, id desc'

    name = fields.Char(
        required=True, readonly=True, copy=False, index=True,
        default=lambda self: _("New"),
    )
    product_id = fields.Many2one(
        'product.product', string="Product", required=True,
        ondelete='restrict', index=True,
    )
    date = fields.Date(
        required=True,
        help="When the goods arrived or were finished. The warranty runs from here.",
    )
    source_type = fields.Selection(
        [('receipt', "Receipt"), ('manufacturing', "Manufacturing")],
        required=True,
    )
    picking_id = fields.Many2one(
        'stock.picking', string="Receipt", ondelete='restrict', index=True,
    )
    production_id = fields.Many2one(
        'mrp.production', string="Manufacturing Order", ondelete='restrict', index=True,
    )
    partner_id = fields.Many2one('res.partner', string="Supplier")
    # Snapshotted from the product at creation rather than read through a
    # related field: the product's policy may change later, and a batch already
    # in customers' hands keeps the terms it was sold under.
    warranty_months = fields.Integer(default=0)
    warranty_end_date = fields.Date(
        compute='_compute_warranty_end_date', store=True,
        help="Empty when the product carries no warranty.",
    )
    lot_ids = fields.One2many('stock.lot', 'batch_id', string="Serial Numbers")
    lot_count = fields.Integer(compute='_compute_lot_count')
    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company,
    )

    # -- computes -----------------------------------------------------------

    @api.depends('date', 'warranty_months')
    def _compute_warranty_end_date(self):
        for batch in self:
            # Zero months is "no warranty", not "a warranty expiring the day it
            # started" -- a date there would read as a real, already-expired term.
            if batch.date and batch.warranty_months > 0:
                batch.warranty_end_date = batch.date + relativedelta(months=batch.warranty_months)
            else:
                batch.warranty_end_date = False

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        counts = dict(self.env['stock.lot']._read_group(
            [('batch_id', 'in', self.ids)], ['batch_id'], ['__count'],
        ))
        for batch in self:
            batch.lot_count = counts.get(batch, 0)

    # -- constraints --------------------------------------------------------

    @api.constrains('lot_ids', 'product_id')
    def _check_lot_product(self):
        """Guard the batch side: serials pushed through ``lot_ids``, and a change
        of ``product_id`` under serials already attached.

        The lot side -- ``batch_id`` written on the serial, which is how the
        receipt and manufacturing hooks actually attach them -- is guarded by
        ``stock.lot._check_batch_product``, which does the comparing for both.
        """
        self.lot_ids._check_batch_product()

    @api.constrains('source_type', 'picking_id', 'production_id')
    def _check_source_document(self):
        """A batch comes from one place, and says which.

        The two document links are alternatives, not a pair: goods either arrived
        on a receipt or came off a manufacturing order. A batch pointing at both
        would give two different answers to "where did this unit come from?", and
        the warranty date it carries is only meaningful against one of them.
        """
        for batch in self:
            if batch.source_type == 'receipt' and batch.production_id:
                raise ValidationError(_(
                    "Batch \"%(batch)s\" is a receipt but is linked to manufacturing "
                    "order %(production)s.",
                    batch=batch.name,
                    production=batch.production_id.display_name,
                ))
            if batch.source_type == 'manufacturing' and batch.picking_id:
                raise ValidationError(_(
                    "Batch \"%(batch)s\" is a manufacturing run but is linked to "
                    "receipt %(picking)s.",
                    batch=batch.name,
                    picking=batch.picking_id.display_name,
                ))

    @api.constrains('warranty_months')
    def _check_warranty_months(self):
        for batch in self:
            if batch.warranty_months < 0:
                raise ValidationError(_(
                    "The warranty on batch \"%(batch)s\" cannot be negative.",
                    batch=batch.name,
                ))

    @api.constrains('date')
    def _check_date_not_in_the_future(self):
        today = fields.Date.context_today(self)
        for batch in self:
            if batch.date and batch.date > today:
                raise ValidationError(_(
                    "Batch \"%(batch)s\" is dated %(date)s, which is in the future. "
                    "A batch records goods that have arrived or been made.",
                    batch=batch.name,
                    date=batch.date,
                ))

    # -- lifecycle ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _("New"):
                # Pass the batch's own date so a backdated batch draws from the
                # right yearly range rather than from today's.
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    SEQUENCE_CODE, sequence_date=vals.get('date'),
                ) or _("New")
        return super().create(vals_list)

    def unlink(self):
        """Deleting a batch that still holds serials would orphan the warranty
        terms of units that are physically in customers' hands."""
        attached = self.filtered('lot_ids')
        if attached:
            raise UserError(_(
                "These batches still have serial numbers attached and cannot be "
                "deleted: %(batches)s\n\nDetach or delete the serial numbers first.",
                batches=", ".join(attached.mapped('name')),
            ))
        return super().unlink()

    # -- creation from a source document ------------------------------------

    @api.model
    def _create_serial_batches(self, lots, source_type, document, date, partner=None):
        """Group ``lots`` into batches under ``document``, one batch per product.

        Shared by the receipt and manufacturing hooks, which differ only in which
        document they hand over and where they read the date from.

        Runs as superuser on purpose. Nobody chooses to create a batch: it is a
        consequence of validating a receipt or closing a manufacturing order, and
        the warehouse operator doing that is not required to hold write access on
        batches themselves.

        Idempotent in two ways, because both hooks can legitimately run twice --
        confirming a backorder wizard re-enters ``button_validate``:

        - lots that already belong to a batch are left alone
        - an existing batch for the same (document, product) pair is reused rather
          than duplicated
        """
        Batch = self.sudo()
        document_field = 'picking_id' if source_type == 'receipt' else 'production_id'

        pending = lots.filtered(lambda lot: not lot.batch_id)
        if not pending:
            return Batch.browse()

        by_product = {}
        for lot in pending:
            by_product.setdefault(lot.product_id, lot.browse())
            by_product[lot.product_id] |= lot

        batches = Batch.browse()
        for product, product_lots in by_product.items():
            batch = Batch.search([
                (document_field, '=', document.id),
                ('product_id', '=', product.id),
                ('company_id', '=', document.company_id.id),
            ], limit=1)
            if not batch:
                batch = Batch.create({
                    'product_id': product.id,
                    'date': date,
                    'source_type': source_type,
                    document_field: document.id,
                    'partner_id': partner.id if partner else False,
                    # Snapshotted now: the product's policy may change later, and
                    # these units keep the terms they arrived under.
                    'warranty_months': product.product_tmpl_id.default_warranty_months,
                    'company_id': document.company_id.id,
                })
            product_lots.sudo().batch_id = batch
            batches |= batch
        return batches

    # -- actions ------------------------------------------------------------

    def action_view_lots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Serial Numbers"),
            'res_model': 'stock.lot',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id, 'default_product_id': self.product_id.id},
        }
