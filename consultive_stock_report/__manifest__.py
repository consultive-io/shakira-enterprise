{
    'name': 'Stock Dashboard & Reports',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Dynamic stock dashboard with per-warehouse daily summary and detailed Excel reports',
    'description': """
Stock Dashboard & Reports
=========================

A dashboard-first stock reporting suite:

* **Stock Dashboard** (onscreen): KPI cards, per-warehouse daily balance
  charts and movement bars, plus per-warehouse daily summary tables.
* **Dynamic report lines**: every run stores product x warehouse x day rows
  that can be pivoted, grouped, filtered and exported from standard views.
* **Excel downloads**: a *Stock Summary* (warehouse blocks x dates) and a
  *Stock Details* (product x warehouse with the full movement breakout), both
  built with xlsxwriter.

Move classification (per warehouse) is driven by location usage pairs and the
move anchors ``production_id`` / ``unbuild_id`` / ``scrap_id`` /
``bom_line_id`` / ``is_inventory``:

* Purchase = supplier in - supplier out (covers returns and returns of returns)
* Manufacture In = MO finished goods - unbuild finished goods
* MO Component = MO raw consumption - unbuild component returns
* Sales = customer out - customer in (covers returns and returns of returns)
* Scraps = scrap moves
* Other Transfers = stock adjustments + internal transfers (signed per
  warehouse: negative means the quantity went out of that warehouse)

Filter priority: BOM > Product > Product Category. Selecting a Product clears
the Product Category (and vice versa), as required by the report spec.
""",
    'author': 'Consultive',
    'license': 'LGPL-3',
    'depends': ['stock', 'mrp'],
    'data': [
        'security/ir.model.access.csv',
        'security/stock_report_security.xml',
        'wizard/stock_report_wizard_views.xml',
        'views/stock_report_line_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'consultive_stock_report/static/src/dashboard/dashboard.scss',
            'consultive_stock_report/static/src/dashboard/dashboard.js',
            'consultive_stock_report/static/src/dashboard/dashboard.xml',
        ],
    },
    'external_dependencies': {'python': ['xlsxwriter']},
    'installable': True,
    'application': False,
}
