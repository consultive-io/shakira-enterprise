# -*- coding: utf-8 -*-
"""Stock report line model and aggregation engine.

Every report run stores ``product x warehouse x day`` rows (``line_type =
'day'``) plus one ``product x warehouse`` total row (``line_type = 'total'``)
for the current user. Rows from previous runs of the same user are cleared on
each new run, so ``user_id`` scopes the table.

Movement buckets (all stored as positive magnitudes, except ``adjustments``
which is signed, and the in/out halves of internal transfers):

=================  =======================================================
Column             Meaning
=================  =======================================================
purchase           receipts from supplier locations
purchase_return    returns to supplier locations (incl. return of return)
manufacture_in     MO finished goods arriving in stock
unbuild            finished goods consumed by unbuild orders
mo_component       MO raw material consumption
mo_component_return raw material returned from MO/unbuild
sales              deliveries to customer locations
sales_return       returns from customer locations
scraps             scrap moves
internal_in        internal transfers in (from another warehouse)
internal_out       internal transfers out (to another warehouse)
adjustments        signed stock adjustments (+in / -out)
repair             repair-order moves (signed); 0 unless ``repair`` is installed
=================  =======================================================
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Buckets that are pure outflows when positive (balance subtracts them)
OUT_BUCKETS = ('unbuild', 'mo_component', 'sales', 'scraps', 'internal_out')


class StockReportLine(models.Model):
    _name = 'stock.report.line'
    _description = 'Stock Report Line'
    _order = 'warehouse_id, line_type, product_id, report_date'
    _rec_name = 'display_name'

    user_id = fields.Many2one(
        'res.users', string='Owner', index=True, required=True,
        default=lambda self: self.env.uid)
    line_type = fields.Selection(
        [('day', 'Daily'), ('total', 'Product Total')],
        required=True, index=True)
    company_id = fields.Many2one('res.company', string='Company')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', index=True)
    product_id = fields.Many2one('product.product', string='Product', index=True)
    categ_id = fields.Many2one(
        'product.category', string='Product Category',
        related='product_id.categ_id', store=True)
    product_uom_id = fields.Many2one(
        'uom.uom', string='UoM', related='product_id.product_tmpl_id.uom_id')
    report_date = fields.Date(string='Date', index=True)
    # Metadata of the run that produced the row (the table is per-user)
    run_id = fields.Integer(string='Wizard Run', index=True)
    run_date_from = fields.Date(string='Run From')
    run_date_to = fields.Date(string='Run To')

    opening_balance = fields.Float(
        string='Opening Balance', digits='Product Unit of Measure')
    purchase = fields.Float(digits='Product Unit of Measure')
    purchase_return = fields.Float(string='P. Return', digits='Product Unit of Measure')
    manufacture_in = fields.Float(
        string='Manufacture In', digits='Product Unit of Measure')
    unbuild = fields.Float(digits='Product Unit of Measure')
    mo_component = fields.Float(
        string='MO Component', digits='Product Unit of Measure')
    mo_component_return = fields.Float(
        string='MO C Return', digits='Product Unit of Measure')
    sales = fields.Float(digits='Product Unit of Measure')
    sales_return = fields.Float(string='Sales Return', digits='Product Unit of Measure')
    scraps = fields.Float(digits='Product Unit of Measure')
    internal_in = fields.Float(
        string='Internal Transfer In', digits='Product Unit of Measure')
    internal_out = fields.Float(
        string='In. Transfer Out', digits='Product Unit of Measure')
    adjustments = fields.Float(digits='Product Unit of Measure')
    repair = fields.Float(digits='Product Unit of Measure')

    display_name = fields.Char(compute='_compute_display_name')

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    def _compute_display_name(self):
        for line in self:
            parts = [
                line.warehouse_id.name or '-',
                line.product_id.display_name or '-',
            ]
            if line.line_type == 'day':
                parts.append(str(line.report_date or ''))
            else:
                parts.append(_('Total'))
            line.display_name = ' | '.join(parts)

    @api.depends(
        'opening_balance', 'purchase', 'purchase_return', 'manufacture_in',
        'unbuild', 'mo_component', 'mo_component_return', 'sales',
        'sales_return', 'scraps', 'internal_in', 'internal_out', 'adjustments',
        'repair')
    def _compute_report_values(self):
        for line in self:
            # All movement columns are signed deltas (+ in / - out), so the
            # nets are plain sums. The Excel report converts them back to the
            # sheet's magnitude convention.
            line.net_purchase = line.purchase + line.purchase_return
            line.net_manufacture = line.manufacture_in + line.unbuild
            line.net_consumption = line.mo_component + line.mo_component_return
            line.net_sales = line.sales + line.sales_return
            line.other_transfers = (
                line.adjustments + line.internal_in + line.internal_out
                + line.repair)
            line.balance = (
                line.opening_balance
                + line.net_purchase
                + line.net_manufacture
                + line.net_consumption
                + line.net_sales
                + line.scraps
                + line.other_transfers)

    net_purchase = fields.Float(
        string='Net Purchase', compute='_compute_report_values',
        digits='Product Unit of Measure')
    net_manufacture = fields.Float(
        string='Net Manufacture', compute='_compute_report_values',
        digits='Product Unit of Measure')
    net_consumption = fields.Float(
        string='Net Consumption', compute='_compute_report_values',
        digits='Product Unit of Measure')
    net_sales = fields.Float(
        string='Net Sales', compute='_compute_report_values',
        digits='Product Unit of Measure')
    other_transfers = fields.Float(
        string='Other Transfers', compute='_compute_report_values',
        digits='Product Unit of Measure')
    balance = fields.Float(
        string='Balance', compute='_compute_report_values',
        digits='Product Unit of Measure')

    # ------------------------------------------------------------------
    # Dashboard data
    # ------------------------------------------------------------------

    def _user_lines(self):
        return self.sudo().search([('user_id', '=', self.env.uid)])

    _BUCKETS = (
        'purchase purchase_return manufacture_in unbuild mo_component '
        'mo_component_return sales sales_return scraps internal_in '
        'internal_out adjustments repair').split()

    @api.model
    def _build_summary(self):
        """Per-warehouse, per-day roll-up of the current user's last run.

        Single source of truth for the dashboard and the Summary Excel.
        Every date of the run window is present (days without movement
        carry the balance forward). Raw bucket values are signed
        (+ in / - out); the ``net_*`` keys follow the report spec's
        presentation (outflows shown as positive magnitudes, Other
        Transfers signed per warehouse).
        """
        lines = self._user_lines()
        if not lines:
            return []
        date_from = lines[0].run_date_from
        date_to = lines[0].run_date_to
        buckets = self._BUCKETS
        result = []
        warehouses = sorted(lines.mapped('warehouse_id'), key=lambda w: w.name)
        for wh in warehouses:
            wh_lines = lines.filtered(lambda l: l.warehouse_id == wh)
            running = sum(
                wh_lines.filtered(lambda l: l.line_type == 'total')
                .mapped('opening_balance'))
            by_date = defaultdict(lambda: dict.fromkeys(buckets, 0.0))
            for line in wh_lines.filtered(lambda l: l.line_type == 'day'):
                for b in buckets:
                    by_date[line.report_date][b] += line[b]
            days = []
            current = date_from
            while current <= date_to:
                raw = by_date[current] if current in by_date \
                    else dict.fromkeys(buckets, 0.0)
                day = {'date': str(current), 'opening_balance': running, **raw}
                signed = {
                    'net_purchase': raw['purchase'] + raw['purchase_return'],
                    'net_manufacture': raw['manufacture_in'] + raw['unbuild'],
                    'net_consumption': (
                        raw['mo_component'] + raw['mo_component_return']),
                    'net_sales': raw['sales'] + raw['sales_return'],
                    'scraps_net': raw['scraps'],
                    'other_transfers': (
                        raw['adjustments'] + raw['internal_in']
                        + raw['internal_out'] + raw['repair']),
                }
                running += sum(signed.values())
                day['balance'] = running
                # Presentation: outflow columns as positive magnitudes
                day.update({
                    'net_purchase': signed['net_purchase'],
                    'net_manufacture': signed['net_manufacture'],
                    'net_consumption': -signed['net_consumption'],
                    'net_sales': -signed['net_sales'],
                    'scraps_shown': -signed['scraps_net'],
                    'other_transfers': signed['other_transfers'],
                })
                days.append(day)
                current += timedelta(days=1)
            result.append({'id': wh.id, 'name': wh.name, 'days': days})
        return result

    @api.model
    def get_dashboard_data(self):
        """Aggregate the current user's generated lines for the dashboard."""
        lines = self._user_lines()
        if not lines:
            return {'kpis': {}, 'warehouses': [], 'filters': None,
                    'run_id': False}
        total_lines = lines.filtered(lambda l: l.line_type == 'total')
        kpi_fields = ['opening_balance'] + list(self._BUCKETS)
        kpis = {f: sum(total_lines.mapped(f)) for f in kpi_fields}
        kpis['balance'] = sum(kpis[f] for f in kpi_fields)
        wizard = self.env['stock.report.wizard'].browse(
            lines[0].run_id).exists()
        return {
            'kpis': kpis,
            'warehouses': self._build_summary(),
            'run_id': lines[0].run_id,
            'filters': wizard and {
                'date_from': str(wizard.date_from),
                'date_to': str(wizard.date_to),
                'categ_ids': wizard.categ_ids.ids,
                'product_ids': wizard.product_ids.ids,
                'bom_ids': wizard.bom_ids.ids,
                'warehouse_ids': wizard.warehouse_ids.ids,
            } or {
                'date_from': str(lines[0].run_date_from),
                'date_to': str(lines[0].run_date_to),
            },
        }

    # ------------------------------------------------------------------
    # Engine: aggregation
    # ------------------------------------------------------------------

    _IN_BUCKETS_SQL = """
        CASE src.usage
            WHEN 'supplier'   THEN 'purchase'
            WHEN 'customer'   THEN 'sales_return'
            WHEN 'production' THEN (CASE
                    WHEN m.unbuild_id IS NOT NULL OR m.bom_line_id IS NOT NULL
                        THEN 'mo_component_return'
                    ELSE 'manufacture_in' END)
            WHEN 'inventory'  THEN 'adjustments'
            WHEN 'internal'   THEN 'internal_in'
            WHEN 'transit'    THEN 'internal_in'
            ELSE NULL END
    """

    _OUT_BUCKETS_SQL = """
        CASE dst.usage
            WHEN 'supplier'   THEN 'purchase_return'
            WHEN 'customer'   THEN 'sales'
            WHEN 'production' THEN (CASE
                    WHEN m.unbuild_id IS NOT NULL AND m.bom_line_id IS NULL
                        THEN 'unbuild'
                    ELSE 'mo_component' END)
            WHEN 'inventory'  THEN (CASE
                    WHEN m.scrap_id IS NOT NULL THEN 'scraps'
                    ELSE 'adjustments' END)
            WHEN 'internal'   THEN 'internal_out'
            WHEN 'transit'    THEN 'internal_out'
            ELSE NULL END
    """

    _BASE_FROM_SQL = """
        FROM stock_move m
        JOIN stock_location src ON src.id = m.location_id
        JOIN stock_location dst ON dst.id = m.location_dest_id
        WHERE m.state = 'done'
          AND m.product_id = ANY(%(product_ids)s)
          AND (m.company_id = %(company_id)s OR m.company_id IS NULL)
          AND m.product_qty != 0
          AND m.date >= %(dt_from)s AND m.date < %(dt_to)s
    """

    def _move_aggregates(self, warehouse, product_ids, dt_from, dt_to,
                         opening=False, tz='UTC'):
        """Return {(product_id, date): {bucket: qty}} or {product_id: qty}.

        In/out halves are computed separately (UNION ALL) so that
        intra-warehouse internal transfers net out to zero and inter-warehouse
        transfers appear as an outflow in the source warehouse and an inflow
        in the destination one.
        """
        internal_ids = self.env['stock.location'].sudo().search([
            ('warehouse_id', '=', warehouse.id),
            ('usage', '=', 'internal'),
        ]).ids
        params = {
            'product_ids': product_ids,
            'company_id': warehouse.company_id.id,
            'internal_ids': internal_ids,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'tz': tz,
        }
        # Repair-order moves are their own bucket when `repair` is installed
        has_repair = 'repair_id' in self.env['stock.move']._fields
        in_bucket = self._IN_BUCKETS_SQL
        out_bucket = self._OUT_BUCKETS_SQL
        if has_repair:
            in_bucket = "(CASE WHEN m.repair_id IS NOT NULL THEN 'repair' ELSE %s END)" % in_bucket
            out_bucket = "(CASE WHEN m.repair_id IS NOT NULL THEN 'repair' ELSE %s END)" % out_bucket
        local_day = "(m.date AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date"
        if opening:
            # Stock position strictly before dt_from
            params['dt_from'] = datetime.min
            params['dt_to'] = dt_from
            sql = """
                SELECT m.product_id,
                       SUM(
                           CASE
                               WHEN dst.id = ANY(%(internal_ids)s)
                                    AND src.id = ANY(%(internal_ids)s) THEN 0
                               WHEN dst.id = ANY(%(internal_ids)s)
                                    THEN m.product_qty
                               WHEN src.id = ANY(%(internal_ids)s)
                                    THEN -m.product_qty
                               ELSE 0
                           END) AS qty
                """ + self._BASE_FROM_SQL + """
                  AND (dst.id = ANY(%(internal_ids)s)
                       OR src.id = ANY(%(internal_ids)s))
                GROUP BY m.product_id
            """
            self.env.cr.execute(sql, params)
            return {row['product_id']: row['qty'] for row in self.env.cr.dictfetchall()}

        params['dt_to'] = dt_to
        sql = f"""
            SELECT t.product_id, t.dt, t.bucket, SUM(t.qty) AS qty
            FROM (
                SELECT m.product_id, {local_day} AS dt,
                       {in_bucket} AS bucket,
                       m.product_qty AS qty
                {self._BASE_FROM_SQL}
                  AND dst.id = ANY(%(internal_ids)s)
                UNION ALL
                SELECT m.product_id, {local_day} AS dt,
                       {out_bucket} AS bucket,
                       -m.product_qty AS qty
                {self._BASE_FROM_SQL}
                  AND src.id = ANY(%(internal_ids)s)
            ) t
            WHERE t.bucket IS NOT NULL
            GROUP BY t.product_id, t.dt, t.bucket
        """
        self.env.cr.execute(sql, params)
        agg = defaultdict(lambda: defaultdict(float))
        for row in self.env.cr.dictfetchall():
            agg[(row['product_id'], row['dt'])][row['bucket']] += row['qty']
        return agg

    @api.model
    def _generate_for_wizard(self, wizard):
        """Generate day rows and total rows for the given wizard."""
        # Raw SQL reads below must see pending ORM writes (e.g. computed
        # product_qty on freshly created moves).
        self.env.flush_all()
        self._user_lines().unlink()

        warehouses = wizard._get_scoped_warehouses()
        products = wizard._get_scoped_products()
        dt_from = wizard._get_dt_from()
        dt_to = wizard._get_dt_to()
        date_from = wizard.date_from
        date_to = wizard.date_to

        buckets = list(self._BUCKETS)
        tz = wizard._user_tz().zone
        run_meta = {
            'run_id': wizard.id,
            'run_date_from': date_from,
            'run_date_to': date_to,
        }

        vals_list = []
        for warehouse in warehouses:
            if not products:
                continue
            opening = self._move_aggregates(
                warehouse, products.ids, dt_from, dt_to, opening=True, tz=tz)
            agg = self._move_aggregates(
                warehouse, products.ids, dt_from, dt_to, tz=tz)

            products_by_date = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
            dates = set()
            for (product_id, dt), bucket_map in agg.items():
                products_by_date[product_id][dt] = bucket_map
                dates.add(dt)

            for product in products:
                opening_base = opening.get(product.id, 0.0)
                product_days = products_by_date.get(product.id, {})
                if opening_base == 0 and not product_days:
                    continue
                running = opening_base
                for dt in sorted(product_days):
                    bucket_map = product_days[dt]
                    if all(bucket_map.get(b, 0.0) == 0 for b in buckets) \
                            and running == 0:
                        continue
                    day_vals = {'opening_balance': running}
                    for bucket in buckets:
                        day_vals[bucket] = bucket_map.get(bucket, 0.0)
                    net = sum(day_vals[b] for b in buckets)
                    running = day_vals['opening_balance'] + net
                    vals_list.append({
                        'user_id': self.env.uid,
                        'line_type': 'day',
                        'company_id': warehouse.company_id.id,
                        'warehouse_id': warehouse.id,
                        'product_id': product.id,
                        'report_date': dt,
                        **day_vals,
                        **run_meta,
                    })
                if opening_base != 0 or product_days:
                    total_vals = {'opening_balance': opening_base}
                    for bucket in buckets:
                        total_vals[bucket] = sum(
                            m.get(bucket, 0.0)
                            for m in product_days.values())
                    vals_list.append({
                        'user_id': self.env.uid,
                        'line_type': 'total',
                        'company_id': warehouse.company_id.id,
                        'warehouse_id': warehouse.id,
                        'product_id': product.id,
                        'report_date': False,
                        **total_vals,
                        **run_meta,
                    })

        # batch create
        for i in range(0, len(vals_list), 500):
            self.sudo().create(vals_list[i:i + 500])
        _logger.info(
            'Stock report generated: %s rows (warehouses=%s, products=%s)',
            len(vals_list), warehouses.ids, products.ids)
        return vals_list
