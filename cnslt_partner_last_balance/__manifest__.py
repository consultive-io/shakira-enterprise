{
    'name': "Partner Last Balance",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': "Show the partner's Due on orders, invoices, bills, credit notes and payments",
    'description': """
Puts the partner's balance on the documents where it is needed, rather than one
click away on the contact.

**Last Balance** appears under the customer or vendor on sales orders, purchase
orders, invoices, bills, credit notes and payments. It is the same figure as the
contact's *Due* button: everything the partner owes you minus everything you
owe them, from posted entries not yet reconciled. Negative means you owe them.

It is read from the field behind that button, never recomputed, so the two can
never disagree.
""",
    'author': "Consultive",
    'license': 'LGPL-3',
    # account_followup provides total_all_due, the field behind the contact's
    # Due button. Depending on it is what guarantees the same number.
    'depends': ['account_followup', 'sale', 'purchase'],
    'data': [
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
}
