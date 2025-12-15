import { Component, onWillStart, useState } from "@inphms/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { browser } from "../../core/browser/browser";
import { _t } from "@web/core/l10n/translation";

const systemInfoRegistry = registry.category("system_info");
const systemInfoDebugRegistry = registry.category("system_info_debug")

export class SystemInformation extends Component {
    static template = "web.SystemInformation";

    setup() {
        this.items = systemInfoRegistry.getAll();
        this.healthService = useService("system_health");
        this.state = useState(this.healthService.state)

        onWillStart(async () => {
            this.healthService.refresh();
        });
    }
    get resolvedItems() {
        return this.items.map(item =>
            typeof item.setup === "function"
                ? item.setup(this.state)
                : item
        );
    }
    get debugToolsActions() {
        const env = this.env;
        return systemInfoDebugRegistry
                .getAll()
                .map(factory => factory({ env }))
                .filter(Boolean);
    }
}

export function registerSystemHealthAction(id, definition) {
    systemInfoRegistry.add(id, definition);
}
registerSystemHealthAction('system_health', {
    setup(state) {
        return {
            label: _t("System health"),
            get value() {
                return state.system.label;
            },
            get level() {
                return state.system.level;
            },
        }
    },
});
registerSystemHealthAction("system_health_database", {
    setup(state) {
        return {
            label: _t("Database"),
            get value() {
                return state.database.label;
            },
            get level() {
                return state.database.level;
            },
        }
    }
});
registerSystemHealthAction("system_health_web_base_url", {
    setup(state) {
        return {
            label: _t("Host"),
            get value() {
                return browser.location.host;
            },
            level: 'neutral'
        }
    }
});

// Actions Developer
import { router } from "@web/core/browser/router";

function activateDebugMode({env}) {
    if (String(router.current.debug).includes("1")) return;
    return {
        label: _t("Activate Debug Mode"),
        callback: () => {
            router.pushState({debug: "1"}, {reload: true});
        },
        sequence: 0,
    }
}
function deactivateDebugMode({env}) {
    if (!String(router.current.debug).includes("1")) return;
    return {
        label: _t("Leave Debug Mode"),
        callback: () => {
            router.pushState({debug: 0}, {reload: true});
        },
        sequence: 0,
    }
}
function systemRegenerateAssets({env}) {
    return {
        label: _t("Regenerate Assets"),
        callback: async () => {
            await env.services.orm.call('ir.attachment', 'regenerate_assets_bundles');
            browser.location.reload();
        },
        sequence: 100,
    }
}
systemInfoDebugRegistry
    .add("activateDebugMode", activateDebugMode)
    .add("deactivateDebugMode", deactivateDebugMode)
    .add("systemRegenerateAssets", systemRegenerateAssets);
