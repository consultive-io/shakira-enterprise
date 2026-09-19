{
    'name': 'Sale Order Fixed Discount',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'author': 'Consultive',
    'summary': 'Allow applying a fixed amount discount on sale order lines',
    'description': """
        This module adds a Fixed Discount field to sales order lines.
        When a fixed discount is entered, the standard discount percentage is calculated automatically.
    """,
    'depends': ['sale_management', 'purchase', 'account'],
    'data': [
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
