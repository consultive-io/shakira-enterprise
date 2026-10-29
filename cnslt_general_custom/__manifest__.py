# -*- coding: utf-8 -*-
{
    'name': "Consultive General Customizations",
    'version': '19.0.1.0.0',
    'category': 'Customizations',
    'summary': "Centralized repository for UI, report, and workflow customizations",
    'description': """
Consultive General Customizations
=================================

Centralized repository for code-managed Studio and UI customizations:

1. **Lot/Serial Number Label Report (42x33mm / 45x35mm)**:
   - Custom paper format: 45mm x 35mm, portrait, 0mm margins, 96 DPI.
   - 3-sticker sheet layout (45x10mm each) with Code128 barcodes, product name, and dynamic company branding.
   - Overrides `stock.action_report_lot_label`.

2. **Manufacturing Order Customizations (`mrp.production`)**:
   - Restricts MO Cancel button (`action_cancel`) to MRP Managers (`mrp.group_mrp_manager`).
   - Ensures Component lines (`move_raw_ids`) explicitly allow create, edit, and delete operations.

Important Notice for Existing Databases:
----------------------------------------
If you previously edited `stock.report_lot_label` directly in the database interface, you can navigate in Odoo to **Settings > Technical > User Interface > Views**, find `stock.report_lot_label`, and click **Compare / Reset to default** so that the base template is clean and the module's inherited view handles the rendering.
Similarly, if you have duplicate Studio customizations for `mrp.production`, you can deactivate or remove them in Studio so this module cleanly governs the architecture.
""",
    'author': "Consultive",
    'license': 'LGPL-3',
    'depends': ['stock', 'mrp'],
    'data': [
        'report/lot_label_report.xml',
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
