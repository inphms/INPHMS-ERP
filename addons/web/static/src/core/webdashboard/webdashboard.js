import { Component } from "@inphms/owl";
// {
//     id: string
//     label: string
//     value: number | string
//     hint?: string
//     sequence?: number
//     onClick?: () => void
// }
export class WebDashboard extends Component {
    static template = "web.WebDashboard";
    static components = {};
    static props = {
        slots: {
            type: Object,
            shape: {
                default: { type: Object, optional: 1 }, // content
                panelTitle: { type: Object },
                panelActions: { type: Object, optional: 1 },
            },
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
                        optional: 1,
                    },
                },
            },
        },
    };

    setup() {
        this.kpiInsight = this.props.kpis;
    }
}
