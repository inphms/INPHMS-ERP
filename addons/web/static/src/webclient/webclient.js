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

        this.serverVersion = session.server_version;
        this.loadingBarRef = useRef("loading-bar");
        this.loadingTextRef = useRef("loading-text");
        this.transition = useTransition({
            name: 'boot-loading',
            leaveDuration: 800,
            onLeave: () => console.log("System Ready. Removing Loader.")
        });
        useEffect(
            (stage) => {
                console.log(stage, "starting")
            },
            () => [this.transition.stage]
        )
        this.bootSequence = {
            interval: null,
            texts: [
                { pct: 15, text: "Waking up AI Agents..." },
                { pct: 30, text: "Loading Leaf Neural Networks..." },
                { pct: 45, text: "Connecting to Plantation Sensors..." },
                { pct: 60, text: "Calibrating Harvest Models..." },
                { pct: 80, text: "Hydrating Dashboard..." },
                { pct: 100, text: "Welcome." }
            ],
            // Phase 1: Asymptotic approach to 65%
            start: () => {
                this.bootSequence.interval = setInterval(() => {
                    // If we are below 65%, grow. If we are close to 65%, grow slower.
                    // This creates a natural "processing" curve.
                    if (this.state.loadingProgress < 65) {
                        const remaining = 65 - this.state.loadingProgress;
                        const step = Math.max(0.5, remaining / 10); // Decaying increment
                        this.updateProgress(this.state.loadingProgress + step);
                    }
                }, 100);
            },
            // Phase 2: Acceleration to 100%
            finish: async () => {
                clearInterval(this.bootSequence.interval);
                return new Promise((resolve) => {
                    const finishInterval = setInterval(() => {
                        const remaining = 100 - this.state.loadingProgress;
                        if (remaining <= 0.5) {
                            this.updateProgress(100);
                            clearInterval(finishInterval);
                            resolve();
                            this.transition.shouldMount = false;
                        } else {
                            // Fast linear fill for satisfaction
                            this.updateProgress(this.state.loadingProgress + (remaining / 4));
                        }
                    }, 30); // High refresh rate for smooth finish
                });
            }
        };

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
        onMounted(async () => {
            await this.loadRouterState();
            // the chat window and dialog services listen to 'web_client_ready' event in
            // order to initialize themselves:
            this.env.bus.trigger("WEB_CLIENT_READY");

            // Loading untrue
            setTimeout(async () => {
                await this.bootSequence.finish();
            }, 1000);
        });
        useExternalListener(window, "click", this.onGlobalClick, { capture: true });
        onWillStart(() => {
            this.registerServiceWorker();
            this.bootSequence.start();
        });
    }

    updateProgress(value) {
        this.state.loadingProgress = value;

        const stage = this.bootSequence.texts.find(t => value <= t.pct && value > (t.pct - 20));
        if (stage && this.state.loadingText !== stage.text) {
             this.state.loadingText = stage.text;
        }
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
