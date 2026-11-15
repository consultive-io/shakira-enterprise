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

from odoo import fields

SUMMARY_HEADERS = [
    'Sl No.', 'Date', 'Opening Balance', 'Net Purchase', 'Net Manufacture',
    'Net Consumption', 'Net Sales', 'Scraps', 'Other Transfers', 'Balance']

DETAILS_HEADERS = [
    'Sl No.', 'Product Name', 'Code', 'Opening Balance', 'Purchase',
    'P. Return', 'Manufacture In', 'Unbuild', 'MO Component', 'MO C Return',
    'Sales', 'Sales Return', 'Scraps', 'Internal Transfer In',
    'In. Transfer Out', 'Adjustments', 'Balance']


def _compute_nets(rec):
    return {
        'net_purchase': rec['purchase'] + rec['purchase_return'],
        'net_manufacture': rec['manufacture_in'] + rec['unbuild'],
        'net_consumption': rec['mo_component'] + rec['mo_component_return'],
        'net_sales': rec['sales'] + rec['sales_return'],
        'other_transfers': rec['adjustments'] + rec['internal_in']
                           + rec['internal_out'] + rec['repair'],
    }


def _compute_balance(rec):
    nets = _compute_nets(rec)
    return (
        rec['opening_balance'] + nets['net_purchase']
        + nets['net_manufacture'] + nets['net_consumption']
        + nets['net_sales'] + rec['scraps'] + nets['other_transfers'])


MAX_LISTED = 25


def _names(records, label='display_name'):
    """Comma-joined names, capped so the header stays readable."""
    names = records.mapped(label)
    shown = ', '.join(names[:MAX_LISTED])
    if len(names) > MAX_LISTED:
        shown += f' ... (+{len(names) - MAX_LISTED} more)'
    return shown


def _criteria_rows(wizard):
    """(label, value) rows describing the selections behind the report."""
    env = wizard.env
    products = wizard._get_scoped_products()
    warehouses = wizard._get_scoped_warehouses()
    fmt = '%d-%b-%Y'
    rows = [('Period', f"{wizard.date_from.strftime(fmt)}  to  "
                       f"{wizard.date_to.strftime(fmt)}")]
    if wizard.datetime_from or wizard.datetime_to:
        rows.append((
            'Time window (UTC)',
            f"{wizard.datetime_from or '-'}  to  {wizard.datetime_to or '-'}"))

    if wizard.bom_ids:
        rows.append(('Selected by', 'Bill of Materials (finished product '
                                    'and components)'))
        rows.append(('Bills of Materials', _names(wizard.bom_ids)))
    elif wizard.product_ids:
        rows.append(('Selected by', 'Products'))
        if wizard.categ_ids:
            rows.append(('Product Categories', _names(wizard.categ_ids)))
    else:
        rows.append(('Selected by', 'Product Categories (all products '
                                    'in the categories)'))
        rows.append(('Product Categories', _names(wizard.categ_ids)))
    if wizard.product_ids:
        rows.append(('Products', _names(wizard.product_ids)))
    rows.append(('Products in report', str(len(products))))
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
    """One block per warehouse, one row per date of the period.

    ``lines`` is kept for signature compatibility; the roll-up comes from
    ``stock.report.line._build_summary`` (shared with the dashboard).
    """
    wb = StockReportWorkbook()
    sheet = wb.workbook.add_worksheet('Stock Summary')
    wb.write_report_criteria(wizard, sheet, 'Stock Summary', last_col=9)
    sheet.write(
        wb.row, 0,
        'A negative Other Transfers means the quantity went out of the '
        'warehouse.', wb.meta_fmt)
    wb.row += 2

    for warehouse in wizard.env['stock.report.line']._build_summary():
        wb.write_period_header(wizard, warehouse['name'], sheet)
        for col, header in enumerate(SUMMARY_HEADERS):
            sheet.write(wb.row, col, header, wb.header_fmt)
        wb.row += 1
        for sl, day in enumerate(warehouse['days'], start=1):
            sheet.write_number(wb.row, 0, sl)
            sheet.write_datetime(
                wb.row, 1, fields.Date.from_string(day['date']), wb.date_fmt)
            values = (
                day['opening_balance'], day['net_purchase'],
                day['net_manufacture'], day['net_consumption'],
                day['net_sales'], day['scraps_shown'],
                day['other_transfers'])
            for col, value in enumerate(values, start=2):
                sheet.write_number(wb.row, col, value, wb.num_fmt)
            sheet.write_number(wb.row, 9, day['balance'], wb.bal_fmt)
            wb.row += 1
        wb.row += 2  # blank rows between blocks

    sheet.freeze_panes(0, 2)
    sheet.set_column(0, 0, 8)
    sheet.set_column(1, 1, 14)
    sheet.set_column(2, 9, 16)
    return wb.close()


def build_details_workbook(wizard, lines):
    wb = StockReportWorkbook()
    sheet = wb.workbook.add_worksheet('Stock Details')
    wb.write_report_criteria(wizard, sheet, 'Stock Details', last_col=16)

    total_lines = lines.filtered(lambda l: l.line_type == 'total')
    warehouses = total_lines.mapped('warehouse_id')

    granular_fields = [
        'opening_balance', 'purchase', 'purchase_return', 'manufacture_in',
        'unbuild', 'mo_component', 'mo_component_return', 'sales',
        'sales_return', 'scraps', 'internal_in', 'internal_out',
        'adjustments', 'repair']
    # Columns displayed as positive magnitudes in the sheet's formula
    # convention (formula subtracts them): stored signed, shown flipped.
    magnitude_columns = {
        'purchase_return', 'unbuild', 'mo_component', 'sales', 'scraps',
        'internal_out'}

    for warehouse in warehouses:
        wb.write_period_header(wizard, warehouse.name, sheet)

        for col, header in enumerate(DETAILS_HEADERS):
            sheet.write(wb.row, col, header, wb.header_fmt)
        wb.row += 1

        sl = 0
        wh_lines = total_lines.filtered(lambda l: l.warehouse_id == warehouse)
        for line in wh_lines.sorted('product_id'):
            sl += 1
            sheet.write_number(wb.row, 0, sl)
            sheet.write(wb.row, 1, line.product_id.display_name)
            sheet.write(wb.row, 2, line.product_id.default_code or '')
            rec = {f: line[f] for f in granular_fields}
            balance = _compute_balance(rec)
            for i, f in enumerate(granular_fields, start=3):
                value = rec[f]
                if f in magnitude_columns:
                    value = -value
                sheet.write_number(wb.row, i, value, wb.num_fmt)
            sheet.write_number(wb.row, 16, balance, wb.bal_fmt)
            wb.row += 1
        wb.row += 2

    sheet.freeze_panes(0, 3)
    sheet.set_column(0, 0, 8)
    sheet.set_column(1, 1, 40)
    sheet.set_column(2, 2, 14)
    sheet.set_column(3, 16, 15)
    return wb.close()
