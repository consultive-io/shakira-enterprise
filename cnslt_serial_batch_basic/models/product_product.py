from odoo import models


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
