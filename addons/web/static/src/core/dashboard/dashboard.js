import { Component, useState } from "@inphms/owl";
import { DashboardSidebar } from "./dashboard_sidebar";

export class Dashboard extends Component {
    static template = "web.Dashboard"
    static components = {
        DashboardSidebar
    }
    static props = {
        slots: {
            type: Object,
            shape: {
                default: {type: Object, optional:1}, // content
                panelTitle: {type: Object},
                panelActions: {type: Object}
            }
        },
        kpis: {
            type: Array,
        },
    }

    setup() {
        
        this.kpiInsight = this.props.kpis;
        console.log(this.kpiInsight);
    }
}