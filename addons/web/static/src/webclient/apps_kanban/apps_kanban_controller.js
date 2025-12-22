import { _t } from "@web/core/l10n/translation";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useService } from "@web/core/utils/hooks";

export class AppsKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService("action");
        console.log("AppsKanbanController setup called", this.actionService);
    }

    get isVisible() {
        return this.env.debug;
    }

    get appsActionButtons() {
        return [
            {
                id: "menu_view_base_module_update", // same as menuitem
                label: _t("Refresh"),
                actionref: "base.action_view_base_module_update",
                help: _t("Update the list of installed apps."),
                btnClass: "btn-primary",
                hotkey: "r",
            },
            {
                id: "menu_view_base_module_upgrade", // same as menuitem
                label: _t("Run"),
                actionref: "base.action_view_base_module_upgrade",
                help: _t("Run any pending module upgrades."),
                btnClass: "btn-secondary",
                hotkey: "shift+r",
            }
        ]
    }

    async onAppsActionButtonClick(action) {
        console.log(this.actionService);
        await this.actionService.doAction(action.actionref);
        console.log("Apps action button clicked:", action);
    }
}