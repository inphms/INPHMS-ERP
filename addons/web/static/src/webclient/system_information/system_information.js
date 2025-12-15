import { Component, reactive } from "@inphms/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

const systemInfoRegistry = registry.category("system_info");

export class SystemInformation extends Component {
    static template = "web.SystemInformation";

    setup() {
        this.items = systemInfoRegistry.getAll();
    }

    get resolvedItems() {
        console.log(this.items);
        return this.items.map(item => ({
            ...item,
            value: typeof item.getValue === "function"
                ? item.getValue()
                : item.value,
            level: typeof item.getLevel === "function"
                ? item.getLevel()
                : item.level,
        }));
    }
}

// {
//   id: "system_health",
//   label: "System health",
//   value: "All services operational",
//   level: "success", // success | warning | danger | neutral
//   actions: [
//     { label: "Debug mode", callback },
//     { label: "Regenerate assets", callback },
//   ]
// }

async function checkHealth(checkDatabase = false) {
    const healthUrl = '/web/health/'
    return await rpc(healthUrl, {
        checkDatabase
    });
}

export function registerSystemHealthAction(id, definition) {
    systemInfoRegistry.add(id, definition);
}
registerSystemHealthAction('system_health', {
    label: _t("System health"),
    getValue: async () => {
        let label;
        try {
            await checkHealth(false).then((res) => {
                if (res.status !== 'pass') {
                    label = "Some services degraded"
                } else {
                    label = "All services operational"
                }
            });
        } catch (err) {
            label = "System unavailable"
        }
        return label;
    },
    getLevel: async () => {
        let level;
        try {
            await checkHealth(false).then((res) => {
                if (res.status !== 'pass') {
                    level = "warning"
                } else {
                    level = "success"
                }
            });
        } catch (err) {
            level = "danger"
        }
        return level;
    },
});

// systemInfoRegistry.add("system_health", {
//     id: "system_health",
//     label: "System health",
//     getValue() {
//         return "All services operational";
//     },
//     level: "success",
// });

systemInfoRegistry.add("database", {
    id: "database",
    label: "Database",
    getValue() {
        return "PostgreSQL · Healthy";
    },
});

systemInfoRegistry.add("host", {
    id: "host",
    label: "Host",
    getValue() {
        return window.location.host;
    },
});
