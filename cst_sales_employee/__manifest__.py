{
    'name': 'Sales Employee Tracking',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Track Sales Employee across Sales Orders, Invoices, and Payments',
    'description': """
        This module adds a 'Sales Employee' field to:
        - Contacts (res.partner)
        - Sales Orders (sale.order)
        - Invoices / Credit Notes (account.move)
        - Payments (account.payment)
        
        The Sales Employee information flows from the Contact to the Sales Order, 
        then to the Invoice, Credit Note, and finally to the Payment.
    """,
    'author': 'TesterArmy',
    'depends': ['sale', 'account', 'hr'],
    'data': [
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
