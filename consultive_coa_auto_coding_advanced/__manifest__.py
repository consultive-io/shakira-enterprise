{
    'name': 'Chart of Accounts Auto Coding - Account Types',
    'summary': 'Derive account group codes from a two-digit account type code',
    'description': """
Chart of Accounts Auto Coding - Account Types
=============================================

Extends *Chart of Accounts Auto Coding* with the level above the group. Account
codes become a three-level scheme::

    account type   06         two digits, configured once
    account group  06001      five digits: type + running serial
    account        06001001   eight digits: group + running serial

Key characteristics:

* ``account_type`` is a Selection in standard Odoo, so it cannot carry a code.
  This module adds ``caac.account.type``, a wrapper model holding exactly one
  record per selection value. Selecting the wrapper fills the standard type, so
  the two can never drift apart.
* Wrapper records are seeded from the live selection, so values added by Odoo or
  by another module are picked up automatically.
* Group codes are generated under the type's code and validated to be exactly
  five characters. The group's prefix fields become read-only once a type is set.
* Codes are per root company, while the wrapper record itself is global, so an
  account spanning several company trees still resolves to one type.
* Standard ``account_type`` stays writable, so chart templates and imports are
  unaffected.
""",
    'author': 'Consultive',
    'website': 'https://consultive.io',
    'category': 'Accounting/Accounting',
    'version': '19.0.1.0.0',
    'license': 'OPL-1',
    'depends': ['consultive_coa_auto_coding_basic'],
    'data': [
        'security/ir.model.access.csv',
        'views/caac_account_type_views.xml',
        'views/account_group_views.xml',
        'views/account_account_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
