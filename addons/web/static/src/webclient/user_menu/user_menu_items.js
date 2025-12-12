import { Component, markup } from "@inphms/owl";
import { isMacOS } from "@web/core/browser/feature_detection";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { browser } from "../../core/browser/browser";
import { registry } from "../../core/registry";

export function supportItem(env) {
    const url = session.support_url;
    return {
        type: "item",
        id: "support",
        description: _t("Help"),
        icon: "fa fa-question-circle-o",
        href: url,
        callback: () => {
            browser.open(url, "_blank");
        },
        sequence: 50,
    };
}

class ShortcutsFooterComponent extends Component {
    static template = "web.UserMenu.ShortcutsFooterComponent";
    static props = {
        switchNamespace: { type: Function, optional: true },
    };
    setup() {
        this.runShortcutKey = isMacOS() ? "CONTROL" : "ALT";
    }
}

export function shortCutsItem(env) {
    return {
        type: "item",
        id: "shortcuts",
        hide: env.isSmall,
        description: markup`
            <div class="d-flex align-items-center justify-content-between p-0 w-100">
                <span>${_t("Shortcuts")}</span>
                <span class="fw-bold">${isMacOS() ? "CMD" : "CTRL"}+K</span>
            </div>`,
        icon: "fa fa-keyboard-o",
        callback: () => {
            env.services.command.openMainPalette({ FooterComponent: ShortcutsFooterComponent });
        },
        sequence: 40,
    };
}

export function separator() {
    return {
        type: "separator",
        sequence: 60,
    };
}

export function separator3() {
    return {
        type: "separator",
        sequence: 80,
    };
}

export function preferencesItem(env) {
    return {
        type: "item",
        id: "preferences",
        description: _t("Preferences"),
        icon: "fa fa-cogs",
        callback: async function () {
            const actionDescription = await env.services.orm.call("res.users", "action_get");
            actionDescription.res_id = user.userId;
            env.services.action.doAction(actionDescription);
        },
        sequence: 30,
    };
}

// export function inphmsAccountItem(env) {
//     return {
//         type: "item",
//         id: "account",
//         description: _t("My Inphms.com Account"),
//         callback: () => {
//             rpc("/web/session/account")
//                 .then((url) => {
//                     browser.open(url, "_blank");
//                 })
//                 .catch(() => {
//                     browser.open("https://accounts.inphms.com/account", "_blank");
//                 });
//         },
//         sequence: 60,
//     };
// }

export function installPWAItem(env) {
    let description = _t("Install App");
    let callback = () => env.services.pwa.show();
    let show = () => env.services.pwa.isAvailable;
    const currentApp = env.services.menu.getCurrentApp();
    if (currentApp && ["barcode", "field-service", "shop-floor"].includes(currentApp.actionPath)) {
        // While the feature could work with all apps, we have decided to only
        // support the installation of the apps contained in this list
        // The list can grow in the future, by simply adding their path
        description = _t("Install %s", currentApp.name);
        callback = () => {
            window.open(
                `/scoped_app?app_id=${currentApp.webIcon.split(",")[0]}&path=${encodeURIComponent(
                    "scoped_app/" + currentApp.actionPath
                )}`
            );
        };
        show = () => !env.services.pwa.isScopedApp;
    }
    return {
        type: "item",
        id: "install_pwa",
        description,
        icon: "fa fa-mobile",
        callback,
        show,
        sequence: 70,
    };
}

export function logOutItem(env) {
    let route = "/web/session/logout";
    if (env.services.pwa.isScopedApp) {
        route += `?redirect=${encodeURIComponent(env.services.pwa.startUrl)}`;
    }
    return {
        type: "item",
        id: "logout",
        description: _t("Log out"),
        icon: "fa fa-sign-out",
        href: `${browser.location.origin}${route}`,
        callback: () => {
            browser.navigator.serviceWorker?.controller?.postMessage("user_logout");
            browser.location.href = route;
        },
        sequence: 90,
    };
}

registry
    .category("user_menuitems")
    .add("support", supportItem)
    .add("shortcuts", shortCutsItem)
    .add("separator", separator)
    .add("preferences", preferencesItem)
    // .add("inphms_account",inphmsAccountItem)
    .add("install_pwa", installPWAItem)
    .add("log_out", logOutItem)
    .add("separator_logout", separator3);
    