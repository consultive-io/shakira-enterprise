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
        self.row = 0

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
