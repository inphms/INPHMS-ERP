import { Component } from "@inphms/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { isRelational } from "@web/model/relational_model/utils";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import {user} from "@web/core/user";

export class GroupConfigMenu extends Component {
    static template = "web.GroupConfigMenu";
    static components = { Dropdown, DropdownItem };
    static props = {
        activeActions: { type: Object },
        configItems: { type: Object },
        deleteGroup: { type: Function },
        dialogClose: { type: Array },
        group: { type: Object },
        list: { type: Object },
    };
    setup() {
        this.dialog = useService("dialog");
        this.orm = useService("orm");
    }

    get configItems() {
        const args = { permissions: this.permissions };
        return this.props.configItems.map(([key, desc]) => ({
            key,
            label: desc.label,
            class: typeof desc.class === "function" ? desc.class(args) : desc.class,
            icon: desc.icon,
            isVisible: typeof desc.isVisible === "function" ? desc.isVisible(args) : desc.isVisible,
            method: typeof desc.method === "function" ? desc.method : this[desc.method].bind(this),
        }));
    }

    get group() {
        return this.props.group;
    }

    get permissions() {
        const permissions = ["canDeleteGroup", "canEditGroup"].reduce((o, key) => {
            Object.defineProperty(o, key, { get: () => this[key]() });
            return o;
        }, {});
        Object.defineProperty(permissions, "canEditAutomations", {
            get: () => user.isAdmin,
            configurable: true,
        });
        return permissions;
    }

    deleteGroup() {
        this.dialog.add(ConfirmationDialog, {
            body: _t("Are you sure you want to delete this column?"),
            confirm: () => this.props.deleteGroup(this.group),
            confirmLabel: _t("Delete"),
            cancel: () => {},
        });
    }

    editGroup() {
        const { context, displayName, groupByField, value } = this.group;
        this.props.dialogClose.push(
            this.dialog.add(FormViewDialog, {
                context,
                resId: value,
                resModel: groupByField.relation,
                title: _t("Edit: %s", displayName),
                onRecordSaved: () => this.props.list.load(),
            })
        );
    }

    canDeleteGroup() {
        const { deleteGroup } = this.props.activeActions;
        const { groupByField, value } = this.group;
        return deleteGroup && isRelational(groupByField) && value;
    }

    canEditGroup() {
        const { editGroup } = this.props.activeActions;
        const { groupByField, value } = this.group;
        return editGroup && isRelational(groupByField) && value;
    }

    async openAutomations() {
        if (typeof this._openAutomations === "function") {
            return this._openAutomations();
        } else {
            this.env.services.dialog.add(PromoteStudioAutomationDialog, {
                title: _t("Inphms Studio - Customize workflows in minutes"),
            });
        }
    }
}

const groupConfigItems = registry.category("group_config_items");
groupConfigItems.add(
    "edit_group",
    {
        label: _t("Edit"),
        isVisible: ({ permissions }) => permissions.canEditGroup,
        class: "o_group_edit",
        icon: "fa-pencil",
        method: "editGroup",
    },
    { sequence: 20 }
);
groupConfigItems.add(
    "delete_group",
    {
        label: _t("Delete"),
        isVisible: ({ permissions }) => permissions.canDeleteGroup,
        class: "o_group_delete text-danger",
        icon: "fa-trash",
        method: "deleteGroup",
    },
    { sequence: 30 }
);
groupConfigItems.add(
    "open_automations",
    {
        label: _t("Automations"),
        method: "openAutomations",
        isVisible: ({permissions}) => permissions.canEditAutomations,
        class: "o_column_automations",
        icon: "fa-magic",
    },
    {
        sequence: 25,
        force: true
    }
)
