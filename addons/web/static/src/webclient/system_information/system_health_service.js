import { registry } from "@web/core/registry";
import { reactive } from "@inphms/owl"
import { browser } from "../../core/browser/browser";
import { _t } from "@web/core/l10n/translation";

export const SystemHealthService = {
    dependencies: [],
    start(env) {
        const state = reactive({
            system: {
                label: 'Checking...',
                level: 'neutral',
            },
            database: {
                label: 'Checking...',
                level: 'neutral',
            },
        });

        async function fetchHealth(checkDatabase) {
            let healthUrl = '/web/health/';
            if (checkDatabase) {
                healthUrl = healthUrl + `?db_server_status=${checkDatabase}`
            }
            const res = await browser.fetch(healthUrl, {
                cache: "no-store",
            });
            return res.json();
        }

        async function _checkHealth(checkDatabase = true) {
            try {
                let res = await fetchHealth(checkDatabase);
                if (res.status !== 'pass') {
                    state.system.label = _t('Some services degraded');
                    state.system.level = 'warning';
                } else {
                    state.system.label = _t('All services operational');
                    state.system.level = 'success';
                }
                if (checkDatabase) {
                    if (res.db_server_status === true) {
                        state.database.label = _t('Connected');
                        state.database.level = 'success';
                    } else {
                        state.database.label = _t('Disconnected');
                        state.database.level = 'danger';
                    }
                } 
            } catch (err) {
                state.system.label = _t('System unavailable');
                state.system.level = 'danger';
                state.database.label = _t('Unknown');
                state.database.level = 'danger';
            }
        }

        return {
            state,
            refresh: _checkHealth
        };
    }
}

registry.category("services").add("system_health", SystemHealthService)