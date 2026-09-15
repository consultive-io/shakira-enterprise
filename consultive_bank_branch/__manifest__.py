{
    'name': "Bank Branches",
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': "Record bank branches and pick the branch on a bank account",
    'description': """
Bank Branches
=============

Adds **Bank Branch** (name and routing number). A bank lists the branches it
has, and a bank account picks its branch from those: choose the bank first, and
the Branch field offers only that bank's branches.

A branch can be listed under more than one bank. Changing an account's bank
clears a branch the new bank does not list, and a branch that does not belong to
the account's bank is refused on save -- including through imports and the API,
which never see the form's filter.
""",
    'author': "Consultive",
    'website': 'https://consultive.io',
    'license': 'LGPL-3',
    'depends': ['contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_bank_branch_views.xml',
        'views/res_bank_views.xml',
        'views/res_partner_bank_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
