import logging

from .models.caac_account_type import account_type_selection, ordered_account_types

_logger = logging.getLogger(__name__)


def _caac_sync_account_types(env):
    """Create a wrapper record for every account type in the live selection.

    Idempotent, so it is safe to re-run from a migration script when a new Odoo
    version or another module adds a type. Codes are left empty: filling them in is
    the one-time configuration the user does after install.
    """
    AccountType = env['caac.account.type']
    labels = dict(account_type_selection(env))
    existing = set(AccountType.search([]).mapped('account_type'))

    values = [
        {
            'name': labels[value],
            'account_type': value,
            'sequence': (index + 1) * 10,
        }
        for index, value in enumerate(ordered_account_types(env))
        if value not in existing
    ]
    if values:
        AccountType.create(values)
    return len(values)


def _caac_backfill_accounts(env):
    """Point existing accounts at the wrapper matching their standard type.

    Unambiguous because there is exactly one wrapper record per type. Nothing about
    the accounts themselves changes -- no code, no type, no report.
    """
    accounts = env['account.account'].with_context(active_test=False).search([
        ('caac_account_type_id', '=', False),
    ])
    if not accounts:
        return 0

    filled = 0
    for account_type in env['caac.account.type'].search([]):
        batch = accounts.filtered(lambda a: a.account_type == account_type.account_type)
        if batch:
            batch.write({'caac_account_type_id': account_type.id})
            filled += len(batch)
    return filled


def post_init_hook(env):
    created = _caac_sync_account_types(env)
    filled = _caac_backfill_accounts(env)
    _logger.info(
        "consultive_coa_auto_coding_advanced: seeded %s account types, "
        "backfilled %s accounts.",
        created, filled,
    )
