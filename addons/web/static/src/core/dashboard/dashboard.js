import {Component} from "@inphms/owl";
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
                default: Object, // content
            }
        }
    }

    setup() {
        
    }
}