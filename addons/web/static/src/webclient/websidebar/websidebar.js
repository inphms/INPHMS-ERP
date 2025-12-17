import { Component, useRef, onWillUnmount, useState } from "@inphms/owl";
import { updateIconSections } from "@web/webclient/navbar/navbar";
import { useService } from "@web/core/utils/hooks";

export class WebSidebar extends Component {
    static template = "web.WebSidebar";
    static components = {};
    static props = [];

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");

        this.state = useState({
            activeMenu: null,
        });

        this.root = useRef("root");
        this.width = "10px";

        const renderAndAdapt = () => {
            console.log("when rendered", this.currentAppSections);
            this.render();
        };
        const updateActiveSelection = async ({ detail: info }) => {
            const currentAction = await this.actionService.currentAction;
            this.state.activeMenu = currentAction.id;
            console.log(currentAction);
        };

        this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", updateActiveSelection);
        this.env.bus.addEventListener("MENUS:APP-CHANGED", renderAndAdapt);
        onWillUnmount(() => {
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", updateActiveSelection);
            this.env.bus.removeEventListener("MENUS:APP-CHANGED", renderAndAdapt);
        });
    }

    get currentApp() {
        return this.menuService.getCurrentApp();
    }
    get currentAppSections() {
        const sections =
            (this.currentApp && this.menuService.getMenuAsTree(this.currentApp.id).childrenTree) ||
            [];
        for (const section of sections) {
            updateIconSections(section);
        }
        return sections;
    }

    async _onDashboardClick() {
        await this.menuService.selectMenu(this.currentApp);
    }
    async _onSectionClick(section) {
        await this.menuService.selectMenu(section);
    }

    _onStartResize(ev) {
        // Triggred only by left mouse button
        if (ev.button !== 0) {
            return;
        }

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
            if (ev.type === "pointerdown" && ev.button === 0) {
                return;
            }
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
        };
        resizeStoppingEvents.forEach((stoppingEvent) => {
            document.addEventListener(stoppingEvent, stopResize, true);
        });
    }
}
