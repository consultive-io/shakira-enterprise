# Stock Dashboard & Reports (`consultive_stock_report`)

Odoo 19 module that produces the **Stock Summary** report: for each warehouse and each date, it shows the opening balance, the movements, and the closing balance. The report is available on screen and as Excel. A per-product **Details** Excel and a dashboard with charts come with it.

- Depends on: `stock`, `mrp`. `repair` is optional (see Repair orders below).
- Python dependency: `xlsxwriter`.
- Menus: **Inventory → Reporting** (Stock Dashboard, Stock Report, Stock Report Lines). Visible to Inventory User and above.

## 1. Using the report

1. Open **Inventory → Reporting → Stock Report**.
2. Fill in the filters:

| Filter | Behaviour |
|---|---|
| From Date / To Date | Required. Days are in your user timezone. |
| Bill of Materials | Highest priority. Reports the BOM's finished product **and its components**. |
| Products | Optional narrowing. With categories chosen, the picker only offers their products. Without categories, picking products locks the Category field. |
| Product Categories | Pick these first. With no product selected, all products of the categories are reported (sub-categories included). |
| Warehouses | Empty means all warehouses of your company. |
| From/To Date with Time | Optional. Overrides the day window for the Details report. |

   At least one of BOM, Product or Category is required. The form enforces these rules:
   - A **BOM** wins over everything: choosing one empties and locks Products and Categories.
   - **Categories come first.** Once categories are chosen, the Products field only offers products of those categories (sub-categories included). Use *Search More* to tick several at once.
   - **No product chosen** means *all products of the selected categories* are reported.
   - **Products chosen** (after a category) means only those products are reported. Changing the categories drops any selected product that is no longer inside them.
   - **Products chosen directly, with no category**: the Category field becomes read-only and is not considered.
   - Category is required only when no BOM and no product is set.

3. Click **Show Dashboard**, **Download Summary (Excel)** or **Download Details (Excel)**.

### Summary (one block per warehouse, one row per date)

| Column | Meaning |
|---|---|
| Opening Balance | Stock at the start of that day (previous day's balance). |
| Net Purchase | Receipts − supplier returns (returns of returns included). |
| Net Manufacture | Finished goods from manufacturing orders − unbuilds. |
| Net Consumption | Raw materials consumed by manufacturing orders − components returned by unbuilds. |
| Net Sales | Deliveries − customer returns (returns of returns included). |
| Scraps | Scrap moves. |
| Other Transfers | Inventory adjustments, internal transfers, repair orders. |
| Balance | Opening + Purchase + Manufacture − Consumption − Sales − Scraps + Other Transfers. |

- Consumption, Sales and Scraps are shown as positive numbers and subtracted in the balance.
- **Other Transfers is signed per warehouse.** A negative value means that quantity left the warehouse.
- Every date in the range appears. Days with no movement carry the balance forward.
- Example from the spec sheet: 100 + 3 + 4 − 4 − 2 = **101**.

### Details (one block per warehouse, one row per product)
Columns: Opening Balance, Purchase, P. Return, Manufacture In, Unbuild, MO Component, MO C Return, Sales, Sales Return, Scraps, Internal Transfer In, In. Transfer Out, Adjustments, Balance. Returns, unbuild, consumption, sales, scraps and transfers out are shown as positive numbers.

### Dashboard
KPI cards for the whole selection, a daily balance line chart and an in/out bar chart per warehouse (gross inflow vs gross outflow), and the daily summary table of each warehouse. The **Filters** button re-opens the wizard.

## 2. How movements are classified

Only `done` stock moves count. A move is classified per warehouse by the **location usage** of its source and destination, relative to that warehouse's internal locations.

| Bucket (stored signed, + in / − out) | Rule |
|---|---|
| `purchase` | supplier → warehouse |
| `purchase_return` | warehouse → supplier |
| `sales` | warehouse → customer |
| `sales_return` | customer → warehouse |
| `manufacture_in` | production → warehouse, not tied to an unbuild or BOM line |
| `unbuild` | warehouse → production, tied to an unbuild order |
| `mo_component` | warehouse → production (raw consumption) |
| `mo_component_return` | production → warehouse, tied to an unbuild order or BOM line |
| `scraps` | warehouse → inventory location, with a scrap record |
| `adjustments` | inventory location ↔ warehouse, without a scrap record |
| `internal_in` / `internal_out` | internal or transit location of another warehouse ↔ this warehouse |
| `repair` | moves of repair orders (only when the `repair` module is installed) |

Notes:
- Transfers inside one warehouse (e.g. stock → sub-location, or a receipt through an input location) net to zero.
- A transfer between two warehouses, including via a transit location, shows as out in the source warehouse and in in the destination.
- Dropship (supplier → customer) is ignored because it never enters a warehouse.
- Opening balance = sum of all done moves before the start of the period, per warehouse.

## 3. Technical design

| File | Role |
|---|---|
| `wizard/stock_report_wizard.py` | Filters, scope rules (BOM > Product > Category), timezone-aware period, download actions. |
| `models/stock_report_line.py` | Aggregation engine (SQL), stored report rows, `_build_summary()` roll-up, `get_dashboard_data()`. |
| `report/stock_report_xlsx.py` | Excel builders for Summary and Details (xlsxwriter). |
| `controllers/main.py` | Download route `/consultive_stock_report/download/<summary|details>/<wizard id>`. |
| `static/src/dashboard/` | OWL dashboard (Chart.js). |
| `views/`, `wizard/*.xml` | List, pivot, graph, search views, menus, wizard form. |
| `security/` | Access rights and the record rule. |
| `tests/test_stock_report.py` | 18 tests. |

How a run works:
1. The wizard resolves the products and warehouses, and converts the dates to a UTC window using the user's timezone.
2. `stock.report.line._generate_for_wizard` deletes the **current user's** previous rows, then stores new ones:
   - `day` rows: product × warehouse × date, **only for dates with movement**.
   - `total` rows: product × warehouse for the whole period, including the opening balance.
3. `_build_summary()` turns these rows into the per-warehouse, per-date table: it starts from the sum of the total rows' openings, walks every date in the range, and carries the balance forward. **The dashboard and the Summary Excel both use it**, so they always agree. Details uses the total rows.

### Security
- Each user can only read their own `stock.report.line` rows (record rule `user_id = user.id`).
- The download route checks that the wizard belongs to the logged-in user.
- Inventory Users can run reports. Inventory Managers have full access to the report tables.

## 4. Known limits

- **One run per user at a time.** Running a new report (or the same user in a second tab) replaces the user's previous rows. A download reuses the current run and only regenerates if the stored run belongs to a different wizard.
- The dashboard opens empty until a report has been run.
- Repair orders get their own bucket only if the `repair` module is installed. Without it, repair moves fall into the other buckets by location usage.
- A BOM selection reports the BOM's finished product and its components, **not** the products of sub-BOMs.
- Large selections (many products × many days) are processed in Python after the SQL step. Prefer a category or BOM filter over "all products".

## 5. Tests

```bash
odoo-bin -c <conf> -d <test_db> -i consultive_stock_report \
    --test-tags /consultive_stock_report --stop-after-init
```

Covered: every movement type, opening balance, quant tie-out, the spec example through the Excel builder, date filling, products with opening but no movement, BOM scope, transit transfers, the timezone day boundary, repair moves and the record rule. The dashboard JS has no automated test.
