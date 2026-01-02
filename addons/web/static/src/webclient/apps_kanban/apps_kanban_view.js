import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { AppsKanbanController } from "./apps_kanban_controller";

/**
 * Simple implementation of, module apps kanban.
 * showing actionable button inside control panel.
 */
const appsKanbanView = {
    ...kanbanView,
    Controller: AppsKanbanController,
    buttonTemplate: "web.AppsKanbanView.buttons",
};

registry.category("views").add("apps_kanban", appsKanbanView);
