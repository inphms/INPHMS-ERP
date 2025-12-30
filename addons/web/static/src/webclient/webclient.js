import { useOwnDebugContext } from "@web/core/debug/debug_context";
import { DebugMenu } from "@web/core/debug/debug_menu";
import { localization } from "@web/core/l10n/localization";
import { MainComponentsContainer } from "@web/core/main_components_container";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { ActionContainer } from "./actions/action_container";
import { NavBar } from "./navbar/navbar";

import { Component, onMounted, onWillStart, useExternalListener, useState, useEffect, useRef } from "@inphms/owl";
import { router, routerBus } from "@web/core/browser/router";
import { browser } from "@web/core/browser/browser";
import { rpcBus } from "@web/core/network/rpc";
import { useTransition } from "@web/core/transition";
import { session } from "@web/session";

export class WebClient extends Component {
    static template = "web.WebClient";
    static props = {};
    static components = {
        ActionContainer,
        NavBar,
        MainComponentsContainer,
    };

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.title = useService("title");
        this.hm = useService("home_menu");

        const bootTexts = [
            { pct: 10, text: "Waking up AI Agents..." },
            { pct: 25, text: "Loading Leaf Neural Networks..." },
            { pct: 40, text: "Connecting to Plantation Sensors..." },
            { pct: 55, text: "Calibrating Harvest Models..." },
            { pct: 70, text: "Authenticating User..."},
            { pct: 85, text: "Hydrating Dashboard..." },
            { pct: 95, text: "System Ready."},
            { pct: 100, text: "Welcome." },
        ];
        this.serverVersion = session.server_version;
        this.loadingBarRef = useRef("loading-bar");
        this.loadingTextRef = useRef("loading-text");
        this.transition = useTransition({
            name: 'boot-loading',
            leaveDuration: 800,
        });
        let isFullyReady = false;
        useEffect(
            (stage) => {
                let nextValue = this.state.loadingProgress;
                switch (stage) {
                    case 'enter-active': {
                        const interval = setInterval(() => {
                            if (!isFullyReady) {
                                const dst = 90 - nextValue;
                                nextValue += dst * 0.05;
                            } else {
                                nextValue += (100 - nextValue) * 0.3;
                                if (nextValue >= 99.5) {
                                    this.state.loadingProgress = 100;
                                    this.state.loadingText = "Welcome.";
                                    clearInterval(interval);
                                    this.transition.shouldMount = false;
                                    return;
                                }
                            }
                            this.state.loadingProgress = nextValue;
                            const currentStage = [...bootTexts].reverse().find(t => nextValue >= t.pct);
                            if (currentStage && this.state.loadingText !== currentStage.text) {
                                this.state.loadingText = currentStage.text;
                            }
                        }, 50);
                        break;
                    }
                    case 'leave': {

                    }
                }
            },
            () => [this.transition.stage]
        )

        useOwnDebugContext({ categories: ["default"] });
        if (this.env.debug) {
            registry.category("systray").add(
                "web.debug_mode_menu",
                {
                    Component: DebugMenu,
                },
                { sequence: 100 }
            );
        }
        this.localization = localization;
        this.state = useState({
            fullscreen: false,
            loadingProgress: 0,
            loadingText: "Initializing System..."
        });
        useBus(routerBus, "ROUTE_CHANGE", async () => {
            document.body.style.pointerEvents = "none";
            try {
                await this.loadRouterState();
            } finally {
                document.body.style.pointerEvents = "auto";
            }
        });
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", ({ detail: mode }) => {
            if (mode !== "new") {
                this.state.fullscreen = mode === "fullscreen";
            }
        });
        useBus(this.env.bus, "WEBCLIENT:LOAD_DEFAULT_APP", this._loadDefaultApp);
        onMounted(() => {
            this.loadRouterState();
            // the chat window and dialog services listen to 'web_client_ready' event in
            // order to initialize themselves:
            this.env.bus.trigger("WEB_CLIENT_READY");

            // Loading untrue
            setTimeout(async () => {
                isFullyReady = true;
            }, 1200);
        });
        useExternalListener(window, "click", this.onGlobalClick, { capture: true });
        onWillStart(() => {
            this.registerServiceWorker();
        });
    }

    async loadRouterState() {
        // ** url-retrocompatibility **
        // the menu_id in the url is only possible if we came from an old url
        let menuId = Number(router.current.menu_id || 0);
        const storedMenuId = Number(browser.sessionStorage.getItem("menu_id"));
        const firstAction = router.current.actionStack?.[0]?.action;
        if (!menuId && firstAction) {
            // Find all menus that match this action
            const matchingMenus = this.menuService
                .getAll()
                .filter((m) => m.actionID === firstAction || m.actionPath === firstAction);

            if (matchingMenus.length > 0) {
                // Use sessionStorage context to determine the correct menu
                menuId = matchingMenus.find(m => 
                    m.appID === storedMenuId
                )?.appID;
                if (!menuId) {
                    menuId = matchingMenus[0]?.appID;
                }
            }
        }
        if (menuId) {
            this.menuService.setCurrentMenu(menuId);
        }
        let stateLoaded = await this.actionService.loadState();

        // ** url-retrocompatibility **
        // when there is only menu_id in url
        if (!stateLoaded && menuId) {
            // Determines the current actionId based on the current menu
            const menu = this.menuService.getAll().find((m) => menuId === m.id);
            const actionId = menu && menu.actionID;
            if (actionId) {
                await this.actionService.doAction(actionId, { clearBreadcrumbs: true });
                stateLoaded = true;
            }
        }

        // Setting the menu based on the action after it was loaded (eg when the action in url is an xmlid)
        if (stateLoaded && !menuId) {
            // Determines the current menu based on the current action
            const currentController = this.actionService.currentController;
            const actionId = currentController && currentController.action.id;
            menuId = this.menuService.getAll().find((m) => m.actionID === actionId)?.appID;
            if (!menuId) {
                // Setting the menu based on the session storage if no other menu was found
                menuId = storedMenuId;
            }
            if (menuId) {
                // Sets the menu according to the current action
                this.menuService.setCurrentMenu(menuId);
            }
        }

        // Scroll to anchor after the state is loaded
        if (stateLoaded) {
            if (browser.location.hash !== "") {
                try {
                    const el = document.querySelector(browser.location.hash);
                    if (el !== null) {
                        el.scrollIntoView(true);
                    }
                } catch {
                    // do nothing if the hash is not a correct selector.
                }
            }
        }

        if (!stateLoaded) {
            // If no action => falls back to the default app
            await this._loadDefaultApp();
        }
    }

    _loadDefaultApp() {
        // // Selects the first root menu if any
        // const root = this.menuService.getMenu("root");
        // const firstApp = root.children[0];
        // if (firstApp) {
        //     return this.menuService.selectMenu(firstApp);
        // }
        return this.hm.toggle(true);
    }

    /**
     * @param {MouseEvent} ev
     */
    onGlobalClick(ev) {
        // When a ctrl-click occurs inside an <a href/> element
        // we let the browser do the default behavior and
        // we do not want any other listener to execute.
        if (
            (ev.ctrlKey || ev.metaKey) &&
            !ev.target.isContentEditable &&
            ((ev.target instanceof HTMLAnchorElement && ev.target.href) ||
                (ev.target instanceof HTMLElement && ev.target.closest("a[href]:not([href=''])")))
        ) {
            ev.stopImmediatePropagation();
            return;
        }
    }

    registerServiceWorker() {
        if (navigator.serviceWorker) {
            navigator.serviceWorker
                .register("/web/service-worker.js", { scope: "/inphms" })
                .then(() => {
                    navigator.serviceWorker.ready.then(() => {
                        if (!navigator.serviceWorker.controller) {
                            // https://stackoverflow.com/questions/51597231/register-service-worker-after-hard-refresh
                            rpcBus.trigger("CLEAR-CACHES");
                        }
                    });
                })
                .catch((error) => {
                    console.error("Service worker registration failed, error:", error);
                });
        }
    }
}
