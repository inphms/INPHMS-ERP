import { Component } from "@inphms/owl";
import { registry } from "@web/core/registry"
import { Dashboard } from "@web/core/dashboard/dashboard";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class PeopleDashboard extends Component {
    static template = "web.PeopleDashboard"
    static components = {Dashboard}
    static props = {...standardActionServiceProps}

    setup() {
        console.log('this setup', this);
    }
}

registry.category("actions").add('action_people_dashboard', PeopleDashboard)