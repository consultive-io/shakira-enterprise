{
    'name': "Serial Numbers & Batch Grouping",
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': "Prefix serial numbers with the item code and group them into batches",
    'description': """
Builds on the item code generator: every physical unit gets a serial number made of
the product's 7-character Internal Reference followed by a 6-digit counter::

    Internal Ref (7):  INFT001
    Serial (13):       INFT001000001

The counter runs per product, so uniqueness across products comes from the prefix,
which the item code generator already guarantees to be unique.

Serial numbers are issued by Odoo's own per-product sequence rather than by a custom
generator, which keeps the barcode app, the receipt and manufacturing wizards, and the
traceability reports working as shipped. This module only decides the prefix and the
padding.
""",
    'author': "Consultive",
    'license': 'LGPL-3',
    'depends': ['cnslt_item_code_generator', 'stock', 'mrp'],
    'data': [
        'security/ir.model.access.csv',
        'security/batch_security.xml',
        'data/ir_sequence_data.xml',
        'views/inventory_serial_batch_views.xml',
        'views/stock_lot_views.xml',
        'views/stock_picking_views.xml',
        'views/mrp_production_views.xml',
        'views/product_views.xml',
    ],
    'installable': True,
}
