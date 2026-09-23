# -*- coding: utf-8 -*-
{
    'name': 'Consultive Sale Fixed Discount Per Unit',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Fixed amount per-unit discount on sales orders',
    'description': """
        Adds a fixed amount discount per unit to sales order lines.
        The discounted unit price drives the line total and flows to invoices.
    """,
    'author': 'Consultive',
    'depends': ['sale'],
    'data': [
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'OPL-1',
}
