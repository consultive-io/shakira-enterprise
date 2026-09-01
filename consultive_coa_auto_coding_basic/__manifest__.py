{
    'name': 'Chart of Accounts Auto Coding',
    'summary': 'Generate account codes automatically from the selected account group',
    'description': """
Chart of Accounts Auto Coding
=============================

Adds an *Account Group* selector on the account form. On save, the account code
is generated as ``<group prefix><zero-padded serial>``, where the serial is the
next available number for that prefix in the active company.

Key characteristics:

* Works with the standard ``account.group`` prefix tree (no parallel hierarchy).
* Serial allocation is stateless (derived from existing codes) and protected by
  a PostgreSQL transaction-level advisory lock, so concurrent creations cannot
  collide.
* Multi-company aware: Odoo 19 stores account codes per root company, and a code
  is generated for every company the account belongs to.
* The generated code is validated to resolve back to the selected group, so a
  child group prefix can never silently capture the new account.
* Accounts can always be switched to manual coding.
""",
    'author': 'Consultive',
    'website': 'https://consultive.io',
    'category': 'Accounting/Accounting',
    'version': '19.0.1.0.1',
    'license': 'OPL-1',
    'depends': ['account'],
    'data': [
        'views/account_group_views.xml',
        'views/account_account_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
