{
    'name': "Account Last Balance",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': "Show each account's balance in the Chart of Accounts list",
    'description': """
Adds a **Balance** column to the Chart of Accounts list: the same figure as the
*Balance* button on each account's form, read from the field behind that button
(current_balance), so the two can never disagree.
""",
    'author': "Consultive",
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_account_views.xml',
    ],
    'installable': True,
}
