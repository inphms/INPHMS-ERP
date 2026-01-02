import { Component, useState, onWillStart } from "@inphms/owl";
import { registry } from "@web/core/registry";
import { WebDashboard } from "@web/core/webdashboard/webdashboard";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { useService } from "@web/core/utils/hooks";
import { ResConfigInviteUsersDialog } from "../settings_form_view/widgets/res_config_invite_users";
import { user } from "@web/core/user";

export class PeopleDashboard extends Component {
    static template = "web.PeopleDashboard";
    static components = { WebDashboard };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.invite = useService("user_invite");
        this.dialog = useService("dialog");
        this.peopleKpiService = useService("people_kpi");

        // this.peopleKpis = useState([]);
        this.state = useState({
            peopleKpis: [],
        });

        onWillStart(async () => {
            const visibleKpis = await this._getVisibleKpis();
            this.state.peopleKpis = visibleKpis.map((kpi) => ({
                id: kpi.id,
                name: kpi.label,
                value: kpi.defaultValue,
                help: kpi.help,
            }));
        });
        this._populateData();
    }

    get peopleKpisRaw() {
        const orm = this.orm;
        const invite = this.invite;
        return [
            {
                id: "total_people",
                label: "Total People",
                defaultValue: 0,
                get value() {
                    return orm.searchCount("res.partner", [
                        ["is_company", "=", false],
                        ["active", "=", true],
                    ]);
                },
                help: "Total Contacts data available on your database.",
                sequence: 0,
            },
            {
                id: "active_users",
                group: "base.group_erp_manager",
                label: "Active Users",
                defaultValue: "...",
                get value() {
                    return orm.searchCount("res.users", [["active", "=", true]]);
                },
                sequence: 10,
            },
            {
                id: "pending_invite",
                group: "base.group_erp_manager",
                label: "Pending Invitations",
                defaultValue: "...",
                get value() {
                    return invite.fetchData(true).then((res) => res.pending_count);
                },
                sequence: 5,
            },
            {
                id: "external_contacts",
                label: "External Contacts",
                defaultValue: "...", // defaultValue cannot be a 0
                get value() {
                    return orm.searchCount("res.partner", [
                        ["is_company", "=", false],
                        ["active", "=", true],
                        ["user_ids", "=", false],
                    ]);
                },
                sequence: 20,
            },
        ];
    }

    // What i can think of, there's 2 way we can solve, the groups visibility.
    // Because of filter and async Promise can't be used together.
    // We either:
    //     1. call the groups endpoint first, and let it be cached.
    //     2. or paralel function that trully filter the visibility
    async _getVisibleKpis() {
        const rawKpis = Object.values(this.peopleKpisRaw);
        const filteredByGroups = await Promise.all(
            rawKpis.map((kpi) => (kpi.group ? user.hasGroup(kpi.group) : true))
        );
        return rawKpis
            .filter((_, i) => filteredByGroups[i])
            .sort((a, b) => a.sequence - b.sequence);
    }
    async _populateData(reload = false) {
        const visibleKpis = await this._getVisibleKpis();
        visibleKpis.map((kpi, index) => {
            this.peopleKpiService
                .fetchData(kpi, reload)
                .then((res) => (this.state.peopleKpis[index].value = res));
        });
    }

    onAddPersonClick() {
        this.env.services.action.doAction({
            res_model: "res.partner",
            type: "ir.actions.act_window",
            views: [[false, "form"]],
            target: "current",
            context: {
                default_is_company: false,
            },
        });
    }
    onInviteUserClick() {
        this.dialog.add(ResConfigInviteUsersDialog, {
            onAction: () => this._populateData(true),
        });
    }
}

registry.category("actions").add("action_people_dashboard", PeopleDashboard);

export const peopleKpisService = {
    async start() {
        const cache = new Map();
        return {
            fetchData(kpi, reload) {
                if (!reload && cache.has(kpi.id)) {
                    return cache.get(kpi.id);
                }
                const promise = Promise.resolve(kpi.value).catch((err) => {
                    console.error(`Error fetching KPI for ${kpi.id}:`, err);
                    return "N/A";
                });
                cache.set(kpi.id, promise);
                return promise;
            },
        };
    },
};
registry.category("services").add("people_kpi", peopleKpisService);
