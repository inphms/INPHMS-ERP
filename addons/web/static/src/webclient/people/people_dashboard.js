import { Component, useState, onWillStart } from "@inphms/owl";
import { registry } from "@web/core/registry"
import { Dashboard } from "@web/core/dashboard/dashboard";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { useService } from "@web/core/utils/hooks";
import { executeButtonCallback } from "@web/views/view_button/view_button_hook";
import { ResConfigInviteUsersDialog } from "../settings_form_view/widgets/res_config_invite_users";

export class PeopleDashboard extends Component {
    static template = "web.PeopleDashboard"
    static components = {Dashboard}
    static props = {...standardActionServiceProps}

    setup() {
        this.orm = useService('orm');
        this.invite = useService('user_invite');
        this.dialog = useService('dialog');
        this.peopleKpiService = useService("people_kpi");
        this.peopleKpis = [];
        this._populateData();
    }

    get peopleKpisRaw() {
        const orm = this.orm;
        const invite = this.invite
        return [
            {
                id: 'total_people',
                label: 'Total People',
                defaultValue: 0,
                get value() {
                    return orm.searchCount(
                            'res.partner',
                            [['is_company', '=', false],
                            ['active', '=', true],]);
                },
                help: "Total Contacts data available on your database.",
                sequence: 0,
            },
            {
                id: 'active_users',
                label: 'Active Users',
                defaultValue: '...',
                get value() {
                    return orm.searchCount('res.users', [['active', '=', true],]);
                },
                sequence: 10,
            },
            {
                id: 'pending_invite',
                label: 'Pending Invitations',
                defaultValue: '...',
                get value() {
                    return invite.fetchData().then((res) => res.pending_count);
                },
                sequence: 5,
            },
            {
                id: 'external_contacts',
                label: 'External Contacts',
                defaultValue: '...', // defaultValue cannot be a 0
                get value() {
                    return orm.searchCount(
                            'res.partner',
                            [['is_company', '=', false],
                            ['active', '=', true],
                            ['user_ids', '=', false]]);
                },
                sequence: 20,
            }
        ]
    }

    _populateData(reload = false) {
        const sortedKpis = Object.values(this.peopleKpisRaw)
            .sort((a, b) => a.sequence - b.sequence);
        for (const kpi of sortedKpis) {
                const kpiItem = useState({
                id: kpi.id,
                name: kpi.label,
                value: kpi.defaultValue,
                help: kpi.help,
            });
            this.peopleKpis.push(kpiItem);
            this.peopleKpiService.fetchData(kpi).
                then((res) => kpiItem.value = res)
        }
    }

    onAddPersonClick() {
        this.env.services.action.doAction({
            res_model: 'res.partner',
            type: 'ir.actions.act_window',
            views: [[false, 'form']],
            target: 'current',
            context: {
                default_is_company: false,
            },
        });
    }
    onInviteUserClick() {
        this.dialog.add(
            ResConfigInviteUsersDialog,
        )
    }
}

registry.category("actions").add('action_people_dashboard', PeopleDashboard);

export const peopleKpisService = {
    async start() {
        const kpis = {};
        return {
            fetchData(kpi, reload) {
                if (!kpis[kpi.id] || reload) {
                    kpis[kpi.id] = Promise.resolve(kpi.value)
                        .catch((err) => {
                            console.error(`Error fetching KPI for ${kpi.id}:`, err);
                            return "N/A"
                        });
                }
                return kpis[kpi.id]
            }
        }
    }
}
registry.category("services").add("people_kpi", peopleKpisService);
