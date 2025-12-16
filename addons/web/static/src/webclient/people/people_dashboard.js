import { Component, useState } from "@inphms/owl";
import { registry } from "@web/core/registry"
import { Dashboard } from "@web/core/dashboard/dashboard";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { useService } from "@web/core/utils/hooks";

export class PeopleDashboard extends Component {
    static template = "web.PeopleDashboard"
    static components = {Dashboard}
    static props = {...standardActionServiceProps}

    setup() {
        this.orm = useService('orm');
        this.peopleKpis = [];
        this._populateData();
    }

    get peopleKpisRaw() {
        return [
            {
                model_name: 'res.partner',
                label: 'Total People',
                domain: [
                    ['is_company', '=', false],
                    ['active', '=', true],
                ],
                get value() {
                    console.log(this.domain, this.orm),
                }
            }
        ]
    }

    _populateData() {
        for (const kpi of this.peopleKpisRaw) {
            const kpiItem = useState({
                name: kpi.label,
                value: 0,
            });
            this.peopleKpis.push(kpiItem)
            this.orm.searchCount(kpi.model_name, kpi.domain)
                .then((res) => kpiItem.value = res)
                .catch((err) => kpiItem.value = err);
        }
    }
}

registry.category("actions").add('action_people_dashboard', PeopleDashboard)