/**
 * TODO:
 * CLEAN THIS AS WE'RE NOT USING THIS ANYMORE.
 */


import { ActionSidebar } from "@web/webclient/actions/action_sidebar";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(ActionSidebar.prototype, {
    setup() {
        super.setup();
        this.store = useService('mail.store');
    },

    get isDiscussApp() {
        return this.store.discuss.isActive;
    }
})