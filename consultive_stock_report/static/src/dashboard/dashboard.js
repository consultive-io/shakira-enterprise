/** @odoo-module **/

import { Component, useEffect, onWillUnmount, onWillStart, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class StockDashboard extends Component {
    static template = "consultive_stock_report.StockDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this.state = useState({
            loading: true,
            data: null,
            error: "",
        });
        this.charts = [];
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadData();
        });
        // (Re)draw the charts whenever the report data changes and the DOM
        // is attached (this.el is not reliable in client actions).
        useEffect(
            (data) => {
                if (data && this.rootRef.el) {
                    this.renderAllCharts();
                }
            },
            () => [this.state.data]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "stock.report.line", "get_dashboard_data", [], {});
            this.state.error = "";
        } catch (error) {
            this.state.error = error?.data?.message || String(error);
            this.state.data = null;
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        await this.loadData();
        // The useEffect in setup() re-renders the charts on data change.
    }

    // ------------------------------------------------------------------
    // Formatting helpers
    // ------------------------------------------------------------------

    fmt(value) {
        if (value === undefined || value === null || isNaN(value)) {
            return "-";
        }
        return new Intl.NumberFormat(undefined, {
            maximumFractionDigits: 2,
        }).format(value);
    }

    get kpiCards() {
        const kpis = this.state.data?.kpis || {};
        const sum = (...keys) => keys.reduce((a, k) => a + (kpis[k] || 0), 0);
        // Server values are signed (+ in / - out); outflow cards are shown
        // as positive magnitudes, like the report spec.
        return [
            { label: _t("Opening Balance"), value: kpis.opening_balance || 0, color: "o_stock_grey" },
            { label: _t("Net Purchase"), value: sum("purchase", "purchase_return"), color: "o_stock_blue" },
            { label: _t("Net Manufacture"), value: sum("manufacture_in", "unbuild"), color: "o_stock_teal" },
            { label: _t("Net Consumption"), value: -sum("mo_component", "mo_component_return"), color: "o_stock_orange" },
            { label: _t("Net Sales"), value: -sum("sales", "sales_return"), color: "o_stock_purple" },
            { label: _t("Scraps"), value: -sum("scraps"), color: "o_stock_red" },
            { label: _t("Other Transfers"), value: sum("adjustments", "internal_in", "internal_out", "repair"), color: "o_stock_brown" },
            { label: _t("Balance"), value: kpis.balance || 0, color: "o_stock_green" },
        ];
    }

    get filterSummary() {
        const data = this.state.data;
        if (!data) {
            return "";
        }
        return `${data.filters?.date_from || ""} → ${data.filters?.date_to || ""}`;
    }

    // ------------------------------------------------------------------
    // Charts
    // ------------------------------------------------------------------

    async renderAllCharts() {
        this.destroyCharts();
        if (!this.state.data) {
            return;
        }
        await this.renderBalanceChart();
        await this.renderMovementChart();
    }

    destroyCharts() {
        for (const chart of this.charts) {
            chart?.destroy();
        }
        this.charts = [];
    }

    get rootEl() {
        return this.rootRef.el;
    }

    renderBalanceChart() {
        const canvas = this.rootEl?.querySelector("#o_stock_balance_chart");
        const data = this.state.data;
        if (!canvas || !data) {
            return;
        }
        const warehouses = data.warehouses || [];
        if (!warehouses.length) {
            return;
        }
        // Union of all dates across warehouses
        const dateSet = new Set();
        for (const wh of warehouses) {
            for (const day of wh.days || []) {
                dateSet.add(day.date);
            }
        }
        const dates = [...dateSet].sort();
        const datasets = warehouses.map((wh, i) => {
            const byDate = Object.fromEntries(
                (wh.days || []).map((d) => [d.date, d.balance]));
            return {
                label: wh.name,
                data: dates.map((d) => byDate[d] ?? null),
                tension: 0.3,
                fill: false,
                borderWidth: 2,
            };
        });
        this.charts.push(new Chart(canvas, {
            type: "line",
            data: { labels: dates, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: false } },
                plugins: {
                    title: { display: true, text: _t("Daily Balance per Warehouse") },
                },
            },
        }));
    }

    renderMovementChart() {
        const canvas = this.rootEl?.querySelector("#o_stock_movement_chart");
        const data = this.state.data;
        if (!canvas || !data) {
            return;
        }
        const warehouses = data.warehouses || [];
        if (!warehouses.length) {
            return;
        }
        // Gross flow per warehouse: every signed bucket value of every day
        // counts as inflow (>0) or outflow (<0), so nothing is netted away.
        const buckets = [
            "purchase", "purchase_return", "manufacture_in", "unbuild",
            "mo_component", "mo_component_return", "sales", "sales_return",
            "scraps", "internal_in", "internal_out", "adjustments", "repair"];
        const labels = warehouses.map((wh) => wh.name);
        const flow = (wh, sign) => (wh.days || []).reduce(
            (acc, day) => acc + buckets.reduce((a, key) => {
                const v = day[key] || 0;
                return a + (v * sign > 0 ? v : 0);
            }, 0), 0);
        const datasets = [
            { label: _t("In"), data: warehouses.map((wh) => flow(wh, 1)), backgroundColor: "#28a745", stack: "flow" },
            { label: _t("Out"), data: warehouses.map((wh) => flow(wh, -1)), backgroundColor: "#dc3545", stack: "flow" },
        ];
        this.charts.push(new Chart(canvas, {
            type: "bar",
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { stacked: true },
                    y: { stacked: true },
                },
                plugins: {
                    title: { display: true, text: _t("Stock In vs Out per Warehouse") },
                },
            },
        }));
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    openFilters() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Stock Report Filters"),
            res_model: "stock.report.wizard",
            views: [[false, "form"]],
            target: "new",
            context: { dialog_size: "large" },
        });
    }

    openLines(viewType = "list") {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Stock Report Lines"),
            res_model: "stock.report.line",
            view_mode: "list,pivot,graph",
            views: [[false, viewType]],
            domain: [["user_id", "=", this.sessionUid]],
            context: { search_default_day_rows: 1 },
        });
    }

    prepareDownload(kind) {
        const runId = this.state.data?.run_id;
        if (!runId) {
            return;
        }
        window.location.href =
            `/consultive_stock_report/download/${kind}/${runId}`;
    }

    get sessionUid() {
        return user.userId;
    }
}

registry.category("actions").add(
    "consultive_stock_report.stock_dashboard", StockDashboard);
