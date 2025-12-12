import { EventBus } from "@inphms/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

export const presenceService = {
    start(env) {
        const LOCAL_STORAGE_PREFIX = "presence";
        const bus = new EventBus();
        let isInphmsFocused = true;
        let lastPresenceTime =
            browser.localStorage.getItem(`${LOCAL_STORAGE_PREFIX}.lastPresence`) ||
            luxon.DateTime.now().ts;

        function onPresence() {
            lastPresenceTime = luxon.DateTime.now().ts;
            browser.localStorage.setItem(`${LOCAL_STORAGE_PREFIX}.lastPresence`, lastPresenceTime);
            bus.trigger("presence");
        }

        function onFocusChange(isFocused) {
            try {
                isFocused = parent.document.hasFocus();
            } catch {
                // noop
            }
            isInphmsFocused = isFocused;
            browser.localStorage.setItem(`${LOCAL_STORAGE_PREFIX}.focus`, isInphmsFocused);
            if (isInphmsFocused) {
                lastPresenceTime = luxon.DateTime.now().ts;
                env.bus.trigger("window_focus", isInphmsFocused);
            }
        }

        function onStorage({ key, newValue }) {
            if (key === `${LOCAL_STORAGE_PREFIX}.focus`) {
                isInphmsFocused = JSON.parse(newValue);
                env.bus.trigger("window_focus", newValue);
            }
            if (key === `${LOCAL_STORAGE_PREFIX}.lastPresence`) {
                lastPresenceTime = JSON.parse(newValue);
                bus.trigger("presence");
            }
        }
        browser.addEventListener("storage", onStorage);
        browser.addEventListener("focus", () => onFocusChange(true));
        browser.addEventListener("blur", () => onFocusChange(false));
        browser.addEventListener("pagehide", () => onFocusChange(false));
        browser.addEventListener("click", onPresence);
        browser.addEventListener("keydown", onPresence);

        return {
            bus,
            getLastPresence() {
                return lastPresenceTime;
            },
            isInphmsFocused() {
                return isInphmsFocused;
            },
            getInactivityPeriod() {
                return luxon.DateTime.now().ts - this.getLastPresence();
            },
        };
    },
};

registry.category("services").add("presence", presenceService);
