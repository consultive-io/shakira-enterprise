{
    'name': 'MRP Raw Material Filter',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Filter raw materials in BOM and MO by product category',
    'description': """
        This module adds a boolean field 'Is MO Component' on the Product Category.
        Only products belonging to categories with this boolean checked will be available for selection as raw materials in Manufacturing Orders and Bill of Materials.
    """,
    'author': 'TesterArmy',
    'depends': ['mrp', 'stock'],
    'data': [
        'views/product_category_views.xml',
        'views/mrp_bom_views.xml',
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
