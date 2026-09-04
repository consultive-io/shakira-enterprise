from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # Odoo generates serial numbers from a per-product ir.sequence, and
    # product.template._inverse_serial_prefix_format picks that sequence by
    # matching its *prefix string*: it reuses an existing sequence whenever the
    # prefix is already taken. The prefix is the Internal Reference, so two
    # products sharing one would silently share a single serial counter and start
    # issuing duplicate serial numbers to physically different units.
    #
    # The generator already keeps issued codes apart -- the per-category sequence
    # is no_gap -- but nothing stops a manual edit, an import, or an RPC call from
    # setting a colliding code, and only the database can catch every path.
    #
    # Partial rather than a plain unique(default_code): Postgres allows many NULLs
    # under a unique index but treats '' as a real value, so every uncoded product
    # would otherwise collide with every other one.
    _default_code_uniq = models.UniqueIndex(
        "(default_code) WHERE default_code IS NOT NULL AND default_code != ''",
        "The Internal Reference must be unique: two products sharing one would "
        "share a serial number sequence and issue duplicate serial numbers.",
    )
