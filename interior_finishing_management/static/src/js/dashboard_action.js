/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

class IFMDashboard extends Component {
    setup() {
        this.state = useState({ data: null });
        this.root = useRef("root");
        onMounted(async () => {
            await this.loadData();
            this.renderCharts();
        });
    }

    async loadData() {
        const mode = this.props.mode;
        if (mode === "executive") {
            this.state.data = await rpc("/ifm/dashboard/executive", {});
        } else if (mode === "project") {
            this.state.data = await rpc("/ifm/dashboard/project", { project_id: this.props.projectId });
        } else {
            this.state.data = await rpc("/ifm/dashboard/engineer", {});
        }
    }

    renderCharts() {
        if (!window.Chart || !this.state.data || !this.root.el) {
            return;
        }
        const rtl = document.documentElement.dir === "rtl";
        const defaults = { responsive: true, maintainAspectRatio: false };

        const make = (id, config) => {
            const el = this.root.el.querySelector(`#${id}`);
            if (el) {
                // eslint-disable-next-line no-new
                new window.Chart(el, config);
            }
        };

        if (this.props.mode === "executive") {
            make("progressChart", {
                type: "doughnut",
                data: {
                    labels: this.state.data.project_progress.labels,
                    datasets: [{ data: this.state.data.project_progress.values }],
                },
                options: { ...defaults, plugins: { legend: { rtl } } },
            });
            make("expensePaymentChart", {
                type: "bar",
                data: {
                    labels: this.state.data.expense_vs_payment.labels,
                    datasets: [
                        { label: "Expenses", data: this.state.data.expense_vs_payment.expenses },
                        { label: "Payments", data: this.state.data.expense_vs_payment.payments },
                    ],
                },
                options: defaults,
            });
            make("profitTrendChart", {
                type: "line",
                data: {
                    labels: this.state.data.profit_over_time.labels,
                    datasets: [{ label: "Profit", data: this.state.data.profit_over_time.values }],
                },
                options: defaults,
            });
            make("comparisonChart", {
                type: "bar",
                data: {
                    labels: this.state.data.multi_project_comparison.labels,
                    datasets: [
                        { label: "Profit", data: this.state.data.multi_project_comparison.profit },
                        { label: "Cost", data: this.state.data.multi_project_comparison.cost },
                        { label: "Duration", data: this.state.data.multi_project_comparison.duration },
                    ],
                },
                options: defaults,
            });
        } else if (this.props.mode === "project") {
            make("estimatedActualChart", {
                type: "bar",
                data: {
                    labels: this.state.data.estimated_vs_actual.labels,
                    datasets: [
                        { label: "Estimated", data: this.state.data.estimated_vs_actual.estimated },
                        { label: "Actual", data: this.state.data.estimated_vs_actual.actual },
                    ],
                },
                options: defaults,
            });
            make("costBreakdownChart", {
                type: "pie",
                data: {
                    labels: this.state.data.cost_breakdown.labels,
                    datasets: [{ data: this.state.data.cost_breakdown.values }],
                },
                options: defaults,
            });
            make("taskStatusChart", {
                type: "bar",
                data: {
                    labels: this.state.data.task_status.labels,
                    datasets: [{ label: "Tasks", data: this.state.data.task_status.values }],
                },
                options: defaults,
            });
        } else {
            make("engineerTaskChart", {
                type: "bar",
                data: {
                    labels: this.state.data.labels,
                    datasets: [
                        { label: "Assigned", data: this.state.data.assigned },
                        { label: "Completed", data: this.state.data.completed },
                        { label: "Pending", data: this.state.data.pending },
                    ],
                },
                options: defaults,
            });
            make("engineerPerformanceChart", {
                type: "radar",
                data: {
                    labels: this.state.data.labels,
                    datasets: [{ label: "Performance", data: this.state.data.performance }],
                },
                options: defaults,
            });
        }
    }
}

IFMDashboard.template = "ifm.Dashboard";

registry.category("actions").add("ifm_executive_dashboard", {
    Component: IFMDashboard,
    props: { mode: "executive" },
});

registry.category("actions").add("ifm_engineer_dashboard", {
    Component: IFMDashboard,
    props: { mode: "engineer" },
});

registry.category("actions").add("ifm_project_dashboard", {
    Component: IFMDashboard,
    props: (env) => ({ mode: "project", projectId: env.config.action.params.project_id }),
});
