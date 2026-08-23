{
    'name': "Item Code & Internal Reference Generator",
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': "Generate segmented item codes and Internal References for inventory items",
    'description': """
Assembles a classification code from four two-character segments plus a running
sequence, and writes it to the product as an Item Code and an Internal Reference::

    Item Code (11):    [IC][IT][PC][SC][SEQ]
    Internal Ref (7):          [PC][SC][SEQ]

The sequence is drawn per PC+SC (the leaf product category), which is what makes
the Internal Reference unique.
""",
    'author': "Consultive",
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/inventory_classification_views.xml',
        'views/product_views.xml',
    ],
    'installable': True,
}
