import { Component, useState } from "@inphms/owl";
import { DashboardSidebar } from "./dashboard_sidebar";
// {
//     id: string
//     label: string
//     value: number | string
//     hint?: string
//     sequence?: number
//     onClick?: () => void
// }
export class Dashboard extends Component {
    static template = "web.Dashboard"
    static components = {
        DashboardSidebar
    }
    static props = {
        slots: {
            type: Object,
            shape: {
                default: {type: Object, optional: 1}, // content
                panelTitle: {type: Object},
                panelActions: {type: Object, optional: 1}
            }
        },
        kpis: {
            type: Array,
            element: {
                type: Object,
                shape: {
                    id: [Number, String],
                    name: String,
                    value: [Number, String],
                    help: {
                        type: String,
                        optional: 1
                    },
                }
            }
        },
    }

    setup() {
        
        this.kpiInsight = this.props.kpis;
        console.log(this.kpiInsight)
    }
}