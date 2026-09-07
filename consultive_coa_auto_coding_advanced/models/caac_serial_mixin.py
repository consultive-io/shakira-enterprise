from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL


class CaacSerialAllocatorMixin(models.AbstractModel):
    """Serial arithmetic shared by the code generators in this module.

    ``consultive_coa_auto_coding_basic`` carries its own copy of this logic for the
    account level; this module deliberately does not refactor it, so that installing
    the type layer cannot regress the module underneath. Both copies share the
    concurrency limitation documented in the README: the advisory lock serialises
    allocation but, under Odoo's REPEATABLE READ cursors, does not guarantee the
    re-read sees the transaction that just released it.
    """
    _name = 'caac.serial.allocator.mixin'
    _description = "Account Coding Serial Allocator"

    @api.model
    def _caac_lock_prefix(self, company, prefix):
        """Serialise allocation per (root company, prefix).

        Transaction-level: released on commit or rollback, and does not block
        allocation under a different prefix.
        """
        self.env.execute_query(SQL(
            "SELECT pg_advisory_xact_lock(%(company_id)s, hashtext(%(prefix)s))",
            company_id=company.root_id.id,
            prefix=prefix,
        ))

    @api.model
    def _caac_next_serial(self, prefix, width, used_serials, cache=None):
        """Return the next free serial under ``prefix``.

        :param used_serials: serials already committed, as integers.
        :param cache: codes handed out in this transaction but not yet visible to
                      the query that produced ``used_serials``.
        """
        serials = set(used_serials)
        total = len(prefix) + width
        for code in (cache or ()):
            if len(code) == total and code.startswith(prefix) and code[len(prefix):].isdigit():
                serials.add(int(code[len(prefix):]))

        ceiling = 10 ** width - 1
        next_serial = (max(serials) if serials else 0) + 1
        if next_serial > ceiling:
            raise ValidationError(_(
                "Prefix %(prefix)s is exhausted: all %(ceiling)s serials are in use. "
                "Widen the serial, or split this level into further subdivisions.",
                prefix=prefix, ceiling=ceiling,
            ))
        return next_serial

    @api.model
    def _caac_format_code(self, prefix, width, serial):
        return f"{prefix}{serial:0{width}d}"
