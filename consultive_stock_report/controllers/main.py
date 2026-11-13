# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import content_disposition, request


class StockReportController(http.Controller):

    def _get_wizard(self, wid):
        wizard = request.env['stock.report.wizard'].browse(wid)
        if not wizard.exists():
            return None
        # Transient records are user-scoped: only the owner (or a manager
        # with unlinked access) may download.
        if wizard.create_uid != request.env.user:
            return None
        return wizard

    @http.route(
        '/consultive_stock_report/download/<string:kind>/<int:wid>',
        type='http', auth='user', methods=['GET'])
    def download(self, kind, wid, **kw):
        wizard = self._get_wizard(wid)
        if not wizard:
            return request.not_found()

        Line = request.env['stock.report.line']
        lines = Line._user_lines()
        # Only regenerate when the stored rows belong to another run; a plain
        # download must not wipe what the dashboard is showing.
        if not lines or lines[0].run_id != wizard.id:
            wizard._generate_lines()
            lines = Line._user_lines()

        if kind == 'summary':
            from ..report.stock_report_xlsx import build_summary_workbook
            data = build_summary_workbook(wizard, lines)
            filename = f"Stock_Summary_{wizard.date_from}_{wizard.date_to}.xlsx"
        elif kind == 'details':
            from ..report.stock_report_xlsx import build_details_workbook
            data = build_details_workbook(wizard, lines)
            filename = f"Stock_Details_{wizard.date_from}_{wizard.date_to}.xlsx"
        else:
            return request.not_found()

        return request.make_response(
            data,
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument'
                 '.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename)),
                ('Content-Length', str(len(data))),
            ])
