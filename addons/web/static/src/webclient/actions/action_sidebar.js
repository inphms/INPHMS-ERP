import { Component, xml, useEffect, useState, onWillUnmount, useRef } from "@inphms/owl";
import { useService } from "@web/core/utils/hooks";
import { updateIconSections } from "@web/webclient/navbar/navbar";


export class ActionSidebar extends Component {
    static props = {}
    static template = "web.ActionSidebar"

    setup() {
        this.menuService = useService('menu');
        this.hm = useService("home_menu");
        
        this.state = useState({
            activeActionID: false,
            expanded: {},
            sidebarExpanded: true,
        });

        this.root = useRef("root");
        this.width = "10px";

        this.onActionUpdated = async () => {
            const currentActionId = await this.env.services.action.currentAction;
            const actionId = currentActionId?.id;
            if (!actionId) {
                this.state.activeActionID = false;
                return;
            }
            const activeMenu = this.findSidebarItemByAction(actionId);
            this.state.activeActionID = activeMenu?.actionID || false;
        }
        this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", this.onActionUpdated);

        onWillUnmount(() => {
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", this.onActionUpdated);
        });
    }

    async toggleSidebarItem(value) {
        if (value.childrenTree.length) {
            const sidebarState = this.state.expanded[value.id];
            if (sidebarState) {
                delete this.state.expanded[value.id];
            } else {
                this.state.expanded[value.id] = true;
            }
        } 
        if (value.actionID && this.state.activeActionID !== value.actionID) {
            await this.menuService.selectMenu(value);
            this.updateActiveSidebar(value);
        }
    }

    findSidebarItemByAction(actionId) {
        const traverse = (items) => {
            for (const item of items) {
                if (item.actionID === actionId) return item;
                if (item.childrenTree.length) {
                    const found = traverse(item.childrenTree);
                    if (found) return found;
                }
            }
        };
        return traverse(this.currentAppSections);
    }

    updateActiveSidebar(value) {
        if (!value.actionID) return;
        this.state.activeActionID = value.actionID;
    }

    get currentAppSections() {
        const sections = (
            (this.menuService.getMenuAsTree('root').childrenTree) ||
            []
        );
        for (const section of sections) {
            updateIconSections(section);
        }
        const sidebar = sections.filter(item => item.xmlid === 'base.sidebar_root');
        console.log(sidebar)
        return sidebar[0].childrenTree || [];
    }

    get isInHomeMenu() {
        return this.hm.hasHomeMenu;
    }

    _onStartResize(ev) {
        // Triggred only by left mouse button
        if (ev.button !== 0) return;

        const initialX = ev.pageX;
        const initialWidth = this.root.el.offsetWidth;
        const resizeStoppingEvents = ["keydown", "pointerdown", "pointerup"];

        const resizeSidebar = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            const maxWidth = Math.max(0.5 * window.innerWidth, initialWidth);
            const delta = ev.pageX - initialX;
            const newWidth = Math.min(maxWidth, Math.max(10, initialWidth + delta));
            this.width = `${newWidth}px`;
            this.root.el.style["min-width"] = this.width;
        };
        document.addEventListener("pointermove", resizeSidebar, true);

        const stopResize = (ev) => {
            // ignore initial left mouse button down.
            if (ev.type === 'pointerdown' && ev.button === 0) return;
            ev.preventDefault();
            ev.stopPropagation();

            document.removeEventListener("pointermove", resizeSidebar, true);
            resizeStoppingEvents.forEach((stoppingEvent) => {
                document.removeEventListener(stoppingEvent, stopResize, true);
            });
            // we remove the focus to make sure that the there is no focus inside
            // the panel. If that is the case, there is some css to darken the whole
            // thead, and it looks quite weird with the small css hover effect.
            document.activeElement.blur();
        }
        resizeStoppingEvents.forEach((stoppingEvent) => {
            document.addEventListener(stoppingEvent, stopResize, true);
        });
    }
}