/** @odoo-module **/

import { Component, useEffect, onWillUnmount, onWillStart, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const PALETTE = [
    "#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#14b8a6"];
const FLOW_BUCKETS = [
    "purchase", "purchase_return", "manufacture_in", "unbuild",
    "mo_component", "mo_component_return", "sales", "sales_return",
    "scraps", "internal_in", "internal_out", "adjustment_in",
    "adjustment_out", "repair_in", "repair_out"];

export class StockDashboard extends Component {
    static template = "consultive_stock_report.StockDashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.rootRef = useRef("root");
        this.state = useState({
            loading: true,
            data: null,
            error: "",
            period: "day",
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
            () => [this.state.data, this.state.period]
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
        // Transfers include internal transfers, inventory adjustments and
        // repair orders, so the cards add up to the closing balance.
        return [
            { label: _t("Opening Balance"), value: kpis.opening_balance || 0, color: "o_stock_grey" },
            { label: _t("Purchase"), value: sum("purchase", "purchase_return"), color: "o_stock_blue" },
            { label: _t("Manufacturing"), value: sum("manufacture_in", "unbuild"), color: "o_stock_teal" },
            { label: _t("Transfer In"), value: sum("internal_in", "adjustment_in", "repair_in"), color: "o_stock_green" },
            { label: _t("Sales"), value: -sum("sales", "sales_return"), color: "o_stock_purple" },
            { label: _t("Consumption"), value: -sum("mo_component", "mo_component_return"), color: "o_stock_orange" },
            { label: _t("Transfer Out"), value: -sum("internal_out", "adjustment_out", "repair_out"), color: "o_stock_brown" },
            { label: _t("Scraps"), value: -sum("scraps"), color: "o_stock_red" },
            { label: _t("Closing Balance"), value: kpis.balance || 0, color: "o_stock_grey" },
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

    setPeriod(period) {
        this.state.period = period;
    }

    /** Group the daily rows by day or by month (balance = last day). */
    get series() {
        const warehouses = this.state.data?.warehouses || [];
        const monthly = this.state.period === "month";
        const keyOf = (date) => (monthly ? date.slice(0, 7) : date);
        const keys = new Set();
        const balances = warehouses.map((wh) => {
            const map = new Map();
            for (const day of wh.days || []) {
                const key = keyOf(day.date);
                keys.add(key);
                map.set(key, day.balance); // days are ascending: last wins
            }
            return { name: wh.name, map };
        });
        const labelKeys = [...keys].sort();
        const inflow = Object.fromEntries(labelKeys.map((k) => [k, 0]));
        const outflow = Object.fromEntries(labelKeys.map((k) => [k, 0]));
        for (const wh of warehouses) {
            for (const day of wh.days || []) {
                const key = keyOf(day.date);
                for (const bucket of FLOW_BUCKETS) {
                    const v = day[bucket] || 0;
                    if (v > 0) {
                        inflow[key] += v;
                    } else {
                        outflow[key] += -v;
                    }
                }
            }
        }
        const fmtLabel = (key) => {
            if (!monthly) {
                return key;
            }
            const [y, m] = key.split("-");
            return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(
                undefined, { month: "short", year: "numeric" });
        };
        return {
            labels: labelKeys.map(fmtLabel),
            balances: balances.map((b) => ({
                name: b.name,
                data: labelKeys.map((k) => b.map.get(k) ?? null),
            })),
            inflow: labelKeys.map((k) => inflow[k]),
            outflow: labelKeys.map((k) => outflow[k]),
        };
    }

    get chartTheme() {
        const style = getComputedStyle(document.documentElement);
        const text = style.getPropertyValue("--body-color").trim() || "#495057";
        return { text, grid: "rgba(128,128,128,0.15)" };
    }

    commonOptions(title) {
        const theme = this.chartTheme;
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            animation: { duration: 500 },
            plugins: {
                title: {
                    display: true, text: title, color: theme.text,
                    align: "start", font: { size: 14, weight: "600" },
                    padding: { bottom: 12 },
                },
                legend: {
                    position: "bottom",
                    labels: {
                        color: theme.text, usePointStyle: true,
                        pointStyle: "circle", boxWidth: 8,
                    },
                },
                tooltip: {
                    backgroundColor: "rgba(33,37,41,0.92)",
                    padding: 10, cornerRadius: 8, boxPadding: 4,
                    callbacks: {
                        label: (ctx) =>
                            ` ${ctx.dataset.label}: ${this.fmt(ctx.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: theme.text, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
                    border: { display: false },
                },
                y: {
                    grid: { color: theme.grid },
                    ticks: { color: theme.text, callback: (v) => this.fmt(v) },
                    border: { display: false },
                },
            },
        };
    }

    renderBalanceChart() {
        const canvas = this.rootEl?.querySelector("#o_stock_balance_chart");
        if (!canvas || !this.state.data?.warehouses?.length) {
            return;
        }
        const { labels, balances } = this.series;
        const ctx = canvas.getContext("2d");
        const datasets = balances.map((wh, i) => {
            const color = PALETTE[i % PALETTE.length];
            const gradient = ctx.createLinearGradient(0, 0, 0, 300);
            gradient.addColorStop(0, color + "55");
            gradient.addColorStop(1, color + "00");
            return {
                label: wh.name,
                data: wh.data,
                borderColor: color,
                backgroundColor: gradient,
                fill: true,
                tension: 0.35,
                borderWidth: 2.5,
                pointRadius: labels.length > 45 ? 0 : 3,
                pointHoverRadius: 6,
                pointBackgroundColor: color,
            };
        });
        const options = this.commonOptions(
            this.state.period === "month"
                ? _t("Month-end Balance per Warehouse")
                : _t("Daily Balance per Warehouse"));
        this.charts.push(new Chart(canvas, {
            type: "line", data: { labels, datasets }, options,
        }));
    }

    renderMovementChart() {
        const canvas = this.rootEl?.querySelector("#o_stock_movement_chart");
        if (!canvas || !this.state.data?.warehouses?.length) {
            return;
        }
        const { labels, inflow, outflow } = this.series;
        const net = inflow.map((v, i) => v - outflow[i]);
        const options = this.commonOptions(
            this.state.period === "month"
                ? _t("Stock In vs Out by Month")
                : _t("Stock In vs Out by Day"));
        this.charts.push(new Chart(canvas, {
            data: {
                labels,
                datasets: [
                    {
                        type: "bar", label: _t("In"), data: inflow,
                        backgroundColor: "#20c997", borderRadius: 6,
                        maxBarThickness: 28, order: 2,
                    },
                    {
                        type: "bar", label: _t("Out"),
                        data: outflow.map((v) => -v),
                        backgroundColor: "#ff6b6b", borderRadius: 6,
                        maxBarThickness: 28, order: 2,
                    },
                    {
                        type: "line", label: _t("Net"), data: net,
                        borderColor: "#4f46e5", backgroundColor: "#4f46e5",
                        borderWidth: 2.5, tension: 0.35, order: 1,
                        pointRadius: labels.length > 45 ? 0 : 3,
                    },
                ],
            },
            options,
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
            this.notification.add(
                _t("This report has expired. Use Filters to run it again, then download."),
                { type: "warning" });
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
