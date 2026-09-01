import logging

_logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def post_init_hook(env):
    """Backfill ``coding_group_id`` on pre-existing accounts.

    Read-only with respect to codes: it only records which group each existing
    code already resolves to, using standard Odoo's own prefix resolution. Existing
    accounts are set to manual coding so nothing about them changes later.
    """
    Account = env['account.account']
    companies = env['res.company'].search([]).root_id
    total = 0

    for company in companies:
        accounts = Account.with_company(company).with_context(active_test=False).search([
            ('company_ids', 'in', company.ids),
        ])
        for index in range(0, len(accounts), BATCH_SIZE):
            batch = accounts[index:index + BATCH_SIZE]
            for account in batch:
                if account.coding_group_id:
                    continue
                group = account.group_id
                values = {'coding_mode': 'manual'}
                if group:
                    values['coding_group_id'] = group.id
                account.write(values)
                total += 1
            env.cr.flush()

    _logger.info("consultive_coa_auto_coding_basic: backfilled %s existing accounts.", total)
