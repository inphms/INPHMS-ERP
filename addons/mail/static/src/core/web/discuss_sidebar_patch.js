import { DiscussSidebar } from "../public_web/discuss_sidebar";
import { patch } from "@web/core/utils/patch";
import { markEventHandled } from "@web/core/utils/misc";

patch(DiscussSidebar.prototype, {
    get mailboxHeader() {
        return this.store.starred;
    },

    openThreadHeader(ev) {
        markEventHandled(ev, "sidebar.openThread");
        this.mailboxHeader.setAsDiscussThread();
    }
});