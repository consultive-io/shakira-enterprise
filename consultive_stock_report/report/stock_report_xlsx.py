# -*- coding: utf-8 -*-
"""Excel report builders (xlsxwriter).

Two workbooks, per the report spec:

* **Stock Summary** — one sheet, one block per warehouse. Each block shows a
  row per date with: Sl No., Date, Opening Balance, Net Purchase, Net
  Manufacture, Net Consumption, Net Sales, Scraps, Other Transfers, Balance.
  A negative ``Other Transfers`` means the quantity went out of the warehouse.

* **Stock Details** — one sheet, one block per warehouse. Each block shows a
  row per product with the full breakout: Opening Balance, Purchase,
  P. Return, Manufacture In, Unbuild, MO Component, MO C Return, Sales,
  Sales Return, Scraps, Internal Transfer In, In. Transfer Out, Adjustments,
  Balance.
"""

import io

import xlsxwriter

from odoo import _, fields

SUMMARY_HEADERS = [
    'Sl No.', 'Date', 'Product', 'Opening Balance', 'Net Purchase', 'Net Manufacture',
    'Net Consumption', 'Net Sales', 'Scraps', 'Other Transfers', 'Balance']

DETAILS_HEADERS = [
    'Sl No.', 'Product Name', 'Code', 'Opening Balance', 'Purchase',
    'P. Return', 'Manufacture In', 'Unbuild', 'MO Component', 'MO C Return',
    'Sales', 'Sales Return', 'Scraps', 'Internal Transfer In',
    'In. Transfer Out', 'Adjustment In', 'Adjustment Out',
    'Repair In', 'Repair Out',
    'Balance']


def _compute_nets(rec):
    return {
        'net_purchase': rec['purchase'] + rec['purchase_return'],
        'net_manufacture': rec['manufacture_in'] + rec['unbuild'],
        'net_consumption': rec['mo_component'] + rec['mo_component_return'],
        'net_sales': rec['sales'] + rec['sales_return'],
        'other_transfers': (
            rec['adjustment_in'] + rec['adjustment_out']
            + rec['internal_in'] + rec['internal_out']
            + rec.get('repair_in', 0.0) + rec.get('repair_out', 0.0)
            + rec.get('repair', 0.0)),
    }


def _compute_balance(rec):
    nets = _compute_nets(rec)
    return (
        rec['opening_balance'] + nets['net_purchase']
        + nets['net_manufacture'] + nets['net_consumption']
        + nets['net_sales'] + rec['scraps'] + nets['other_transfers'])


MAX_LISTED = 25
MAX_PRODUCTS = 60


def _names(records, label='display_name', limit=MAX_LISTED):
    """Comma-joined names, capped so the header stays readable."""
    names = records.mapped(label)
    shown = ', '.join(names[:limit])
    if len(names) > limit:
        shown += f' ... (+{len(names) - limit} more)'
    return shown


def _criteria_rows(wizard):
    """(label, value) rows describing the selections behind the report."""
    env = wizard.env
    warehouses = wizard._get_scoped_warehouses()
    fmt = '%d-%b-%Y'
    rows = [('Period', f"{wizard.date_from.strftime(fmt)}  to  "
                       f"{wizard.date_to.strftime(fmt)}")]
    if wizard.datetime_from or wizard.datetime_to:
        rows.append((
            'Time window (UTC)',
            f"{wizard.datetime_from or '-'}  to  {wizard.datetime_to or '-'}"))

    # Show only what the user selected: a BOM wins over everything, and
    # categories are listed alone unless products were picked as well.
    if wizard.bom_ids:
        rows.append(('Bills of Materials', _names(wizard.bom_ids)))
    else:
        if wizard.categ_ids:
            rows.append(('Product Categories', _names(wizard.categ_ids)))
        if wizard.product_ids:
            rows.append((
                'Products',
                _names(wizard.product_ids.sorted('display_name'),
                       limit=MAX_PRODUCTS)))
    rows.append(('Company', _names(warehouses.company_id)))
    rows.append((
        'Warehouses',
        _names(wizard.warehouse_ids) if wizard.warehouse_ids
        else f"All warehouses ({_names(warehouses)})"))
    now = fields.Datetime.context_timestamp(wizard, fields.Datetime.now())
    rows.append((
        'Generated', f"{now.strftime('%d-%b-%Y %H:%M')} by {env.user.name}"))
    return rows


class StockReportWorkbook:
    def __init__(self):
        self.output = io.BytesIO()
        self.workbook = xlsxwriter.Workbook(
            self.output, {'in_memory': True})
        self.title_fmt = self.workbook.add_format({
            'bold': True, 'font_size': 14})
        self.block_fmt = self.workbook.add_format({
            'bold': True, 'font_size': 12})
        self.meta_fmt = self.workbook.add_format({'italic': True})
        self.header_fmt = self.workbook.add_format({
            'bold': True, 'bg_color': '#D9E1F2', 'border': 1,
            'text_wrap': True, 'valign': 'vcenter'})
        self.date_fmt = self.workbook.add_format({'num_format': 'dd-mmm-yyyy'})
        self.num_fmt = self.workbook.add_format({'num_format': '#,##0.00'})
        self.bal_fmt = self.workbook.add_format({
            'num_format': '#,##0.00', 'bold': True, 'bg_color': '#E2EFDA',
            'border': 1})
        # Summary: bold date-total rows, muted indented product rows
        self.day_text_fmt = self.workbook.add_format({
            'bold': True, 'bg_color': '#EDEDED', 'top': 1})
        self.day_date_fmt = self.workbook.add_format({
            'bold': True, 'bg_color': '#EDEDED', 'top': 1,
            'num_format': 'dd-mmm-yyyy', 'align': 'left'})
        self.day_num_fmt = self.workbook.add_format({
            'bold': True, 'bg_color': '#EDEDED', 'top': 1,
            'num_format': '#,##0.00'})
        self.day_bal_fmt = self.workbook.add_format({
            'num_format': '#,##0.00', 'bold': True, 'bg_color': '#E2EFDA',
            'top': 1})
        self.categ_fmt = self.workbook.add_format({
            'bold': True, 'bg_color': '#DDEBF7', 'font_size': 11,
            'top': 1, 'bottom': 1})
        self.prod_text_fmt = self.workbook.add_format({'indent': 1})
        self.prod_date_fmt = self.workbook.add_format({
            'num_format': 'dd-mmm-yyyy', 'font_color': '#8C8C8C',
            'align': 'left'})
        self.label_fmt = self.workbook.add_format({
            'bold': True, 'bg_color': '#F2F2F2', 'border': 1,
            'valign': 'top'})
        self.value_fmt = self.workbook.add_format({
            'border': 1, 'text_wrap': True, 'valign': 'top'})
        self.row = 0

    def write_report_criteria(self, wizard, sheet, title, last_col=9):
        """Top block: what this report is for (the user's selections)."""
        sheet.merge_range(self.row, 0, self.row, last_col, title, self.title_fmt)
        self.row += 1
        for label, value in _criteria_rows(wizard):
            sheet.merge_range(self.row, 0, self.row, 1, label, self.label_fmt)
            sheet.merge_range(
                self.row, 2, self.row, last_col, value, self.value_fmt)
            # merged cells do not auto-fit: size the row for wrapped text
            lines = max(1, -(-len(value) // 100))
            sheet.set_row(self.row, 15 * lines)
            self.row += 1
        self.row += 1

    def write_period_header(self, wizard, warehouse_name, sheet):
        sheet.merge_range(
            self.row, 0, self.row, 3, f"Warehouse: {warehouse_name}",
            self.block_fmt)
        self.row += 1
        sheet.merge_range(
            self.row, 0, self.row, 3,
            f"From Date: {wizard.date_from}    To Date: {wizard.date_to}",
            self.meta_fmt)
        self.row += 1
        self.row += 1

    def close(self):
        self.workbook.close()
        return self.output.getvalue()


def build_summary_workbook(wizard, lines):
    """Product by product: every date of the period for each product.

    One block per warehouse (or a single "All Warehouses" block when no
    warehouse was selected). Inside it each product has its own heading and
    one row per date with the product's opening, movements and balance.

    ``lines`` is kept for signature compatibility; the roll-up comes from
    ``stock.report.line._build_product_summary``.
    """
    wb = StockReportWorkbook()
    sheet = wb.workbook.add_worksheet('Stock Summary')
    last_col = len(SUMMARY_HEADERS) - 1
    wb.write_report_criteria(wizard, sheet, 'Stock Summary', last_col=last_col)
    sheet.write(
        wb.row, 0,
        'A negative Other Transfers means the quantity went out of the '
        'warehouse. Each product is listed on its own with a row for every '
        'date of the period.', wb.meta_fmt)
    wb.row += 2

    value_keys = (
        'opening_balance', 'net_purchase', 'net_manufacture',
        'net_consumption', 'net_sales', 'scraps_shown', 'other_transfers')
    summary = wizard.env['stock.report.line']._build_product_summary(
        combine=not wizard.warehouse_ids)
    for warehouse in summary:
        wb.write_period_header(wizard, warehouse['name'], sheet)
        if not warehouse['products']:
            sheet.write(
                wb.row, 0, 'No stock or movement for the selected products '
                'in this period.', wb.meta_fmt)
            wb.row += 1
        for prod in warehouse['products']:
            title = prod['product']
            sheet.merge_range(
                wb.row, 0, wb.row, last_col, f'Product: {title}',
                wb.categ_fmt)
            wb.row += 1
            for col, header in enumerate(SUMMARY_HEADERS):
                sheet.write(wb.row, col, header, wb.header_fmt)
            wb.row += 1
            for sl, day in enumerate(prod['days'], start=1):
                when = fields.Date.from_string(day['date'])
                sheet.write_number(wb.row, 0, sl)
                sheet.write_datetime(wb.row, 1, when, wb.date_fmt)
                sheet.write(wb.row, 2, title)
                for col, key in enumerate(value_keys, start=3):
                    sheet.write_number(wb.row, col, day[key], wb.num_fmt)
                sheet.write_number(wb.row, last_col, day['balance'], wb.bal_fmt)
                wb.row += 1
            wb.row += 1  # blank row between products
        wb.row += 2  # blank rows between warehouse blocks

    sheet.freeze_panes(0, 3)
    sheet.set_column(0, 0, 8)
    sheet.set_column(1, 1, 14)
    sheet.set_column(2, 2, 38)
    sheet.set_column(3, last_col, 16)
    return wb.close()


DETAILS_FIELDS = [
    'opening_balance', 'purchase', 'purchase_return', 'manufacture_in',
    'unbuild', 'mo_component', 'mo_component_return', 'sales',
    'sales_return', 'scraps', 'internal_in', 'internal_out',
    'adjustment_in', 'adjustment_out', 'repair_in', 'repair_out']
# Columns displayed as positive magnitudes in the sheet's formula
# convention (the balance subtracts them): stored signed, shown flipped.
DETAILS_MAGNITUDE = {
    'purchase_return', 'unbuild', 'mo_component', 'sales', 'scraps',
    'internal_out', 'adjustment_out', 'repair_out'}


def _write_details_numbers(sheet, row, rec, num_fmt, bal_fmt):
    """Write the movement columns and the balance of one details row."""
    for col, field in enumerate(DETAILS_FIELDS, start=3):
        value = rec[field]
        if field in DETAILS_MAGNITUDE:
            value = -value
        sheet.write_number(row, col, value, num_fmt)
    sheet.write_number(row, 3 + len(DETAILS_FIELDS), _compute_balance(rec), bal_fmt)


def build_details_workbook(wizard, lines):
    """Warehouse > Category > Product, with category and warehouse totals."""
    wb = StockReportWorkbook()
    sheet = wb.workbook.add_worksheet('Stock Details')
    last_col = len(DETAILS_HEADERS) - 1
    wb.write_report_criteria(wizard, sheet, 'Stock Details', last_col=last_col)

    total_lines = lines.filtered(lambda l: l.line_type == 'total')
    if wizard.warehouse_ids:
        # every selected warehouse gets a block, even without movement
        blocks = [
            (wh.name, total_lines.filtered(lambda l, wh=wh: l.warehouse_id == wh))
            for wh in wizard._get_scoped_warehouses().sorted('name')]
    else:
        # No warehouse selected: one combined block (products summed over
        # the warehouses of the selected company).
        blocks = [(wizard.env._('All Warehouses'), total_lines)]

    for block_name, wh_lines in blocks:
        wb.write_period_header(wizard, block_name, sheet)
        for col, header in enumerate(DETAILS_HEADERS):
            sheet.write(wb.row, col, header, wb.header_fmt)
        wb.row += 1

        categories = wh_lines.mapped('categ_id').sorted('complete_name')
        groups = [(c, wh_lines.filtered(lambda l, c=c: l.categ_id == c))
                  for c in categories]
        no_categ = wh_lines.filtered(lambda l: not l.categ_id)
        if no_categ:
            groups.append((None, no_categ))

        if not groups:
            sheet.write(
                wb.row, 0, 'No stock or movement for the selected products '
                'in this period.', wb.meta_fmt)
            wb.row += 1
        sl = 0
        warehouse_rec = dict.fromkeys(DETAILS_FIELDS, 0.0)
        for categ, categ_lines in groups:
            title = categ.complete_name if categ else 'No category'
            sheet.merge_range(
                wb.row, 0, wb.row, last_col, f'Category: {title}',
                wb.categ_fmt)
            wb.row += 1
            categ_rec = dict.fromkeys(DETAILS_FIELDS, 0.0)
            products = categ_lines.product_id.sorted('display_name')
            for product in products:
                sl += 1
                sheet.write_number(wb.row, 0, sl)
                sheet.write(wb.row, 1, product.display_name)
                sheet.write(wb.row, 2, product.default_code or '')
                prod_lines = categ_lines.filtered(
                    lambda l, p=product: l.product_id == p)
                rec = {f: sum(prod_lines.mapped(f)) for f in DETAILS_FIELDS}
                _write_details_numbers(sheet, wb.row, rec, wb.num_fmt, wb.bal_fmt)
                for f in DETAILS_FIELDS:
                    categ_rec[f] += rec[f]
                wb.row += 1
            for f in DETAILS_FIELDS:
                warehouse_rec[f] += categ_rec[f]
            wb.row += 1
        # warehouse total
        sheet.merge_range(
            wb.row, 0, wb.row, 2, f'Total - {block_name}', wb.header_fmt)
        _write_details_numbers(
            sheet, wb.row, warehouse_rec, wb.bal_fmt, wb.bal_fmt)
        wb.row += 3

    sheet.freeze_panes(0, 3)
    sheet.set_column(0, 0, 8)
    sheet.set_column(1, 1, 40)
    sheet.set_column(2, 2, 14)
    sheet.set_column(3, last_col, 15)
    return wb.close()
