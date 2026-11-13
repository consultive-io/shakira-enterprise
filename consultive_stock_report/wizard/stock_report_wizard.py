# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta
import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockReportWizard(models.TransientModel):
    _name = 'stock.report.wizard'
    _description = 'Stock Report Wizard'
    _order = 'id desc'

    date_from = fields.Date(
        string='From Date', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(
        string='To Date', required=True,
        default=fields.Date.context_today)
    datetime_from = fields.Datetime(
        string='From Date with Time',
        help='Optional precision window for the Details report. '
             'Defaults to the start of From Date.')
    datetime_to = fields.Datetime(
        string='To Date with Time',
        help='Optional precision window for the Details report. '
             'Defaults to the end of To Date.')
    categ_ids = fields.Many2many(
        'product.category', string='Product Categories')
    product_ids = fields.Many2many('product.product', string='Products')
    bom_ids = fields.Many2many('mrp.bom', string='Bills of Materials')
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')

    # ------------------------------------------------------------------
    # Spec rules
    # ------------------------------------------------------------------

    # Rules: BOM wins over everything. Categories come first: with
    # categories chosen, the product picker only offers their products and
    # no product means "all products of those categories". Products chosen
    # directly (no category) lock the category field, which is then ignored.

    @api.onchange('bom_ids')
    def _onchange_bom_ids(self):
        """BOM has first priority: product and category are emptied."""
        if self.bom_ids:
            self.product_ids = self.env['product.product']
            self.categ_ids = self.env['product.category']

    @api.onchange('categ_ids')
    def _onchange_categ_ids(self):
        """Drop selected products that are no longer inside the categories."""
        if self.categ_ids and self.product_ids:
            paths = [c.parent_path for c in self.categ_ids if c.parent_path]
            self.product_ids = self.product_ids.filtered(
                lambda p: any(
                    (p.categ_id.parent_path or '').startswith(path)
                    for path in paths))

    # ------------------------------------------------------------------
    # Scopes
    # ------------------------------------------------------------------

    def _get_scoped_warehouses(self):
        self.ensure_one()
        if self.warehouse_ids:
            warehouses = self.warehouse_ids
        else:
            warehouses = self.env['stock.warehouse'].search([
                ('company_id', 'in', self.env.companies.ids)])
        if not warehouses:
            raise UserError(_('No warehouse available for your company.'))
        return warehouses

    def _get_scoped_products(self):
        self.ensure_one()
        if self.bom_ids:
            # Highest priority: finished products of the selected BOMs plus
            # their components, so consumption is reported too.
            tmpl_ids = self.bom_ids.mapped('product_tmpl_id').ids
            finished = self.env['product.product'].with_context(
                active_test=False).search([
                    ('product_tmpl_id', 'in', tmpl_ids)])
            return finished | self.bom_ids.bom_line_ids.product_id
        if self.product_ids:
            return self.product_ids
        if self.categ_ids:
            # Include sub-categories (category-wise search)
            categs = self.env['product.category']
            for categ in self.categ_ids:
                categs |= self.env['product.category'].search([
                    ('parent_path', '=like', f"{categ.parent_path}%")])
            return self.env['product.product'].search([
                ('categ_id', 'in', categs.ids),
                ('type', '!=', 'service'),
            ])
        raise UserError(_(
            'Select at least a Product Category, a Product or a BOM.'))

    def _user_tz(self):
        self.ensure_one()
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    def _local_midnight_utc(self, day):
        """Naive UTC datetime of local midnight of ``day`` in the user tz."""
        local = self._user_tz().localize(datetime.combine(day, time.min))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _get_dt_from(self):
        self.ensure_one()
        if self.datetime_from:
            return self.datetime_from.replace(tzinfo=None)
        return self._local_midnight_utc(self.date_from)

    def _get_dt_to(self):
        self.ensure_one()
        if self.datetime_to:
            return self.datetime_to.replace(tzinfo=None)
        return self._local_midnight_utc(
            self.date_to + timedelta(days=1))  # exclusive

    def _validate_dates(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('From Date must be before To Date.'))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _generate_lines(self):
        self._validate_dates()
        # touch scopes first so errors surface before any work
        self._get_scoped_warehouses()
        self._get_scoped_products()
        return self.env['stock.report.line']._generate_for_wizard(self)

    def action_run_dashboard(self):
        self._generate_lines()
        return {
            'type': 'ir.actions.client',
            'tag': 'consultive_stock_report.stock_dashboard',
            'name': _('Stock Dashboard'),
            'target': 'main',
        }

    def action_download_summary(self):
        self._generate_lines()
        return self._download_url('summary')

    def action_download_details(self):
        self._generate_lines()
        return self._download_url('details')

    def _download_url(self, kind):
        return {
            'type': 'ir.actions.act_url',
            'url': f'/consultive_stock_report/download/{kind}/{self.id}',
            'target': 'self',
        }
