import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@inphms/owl";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownGroup } from "@web/core/dropdown/dropdown_group";

export class ClockMenu extends Component {
    static components = { DropdownGroup, Dropdown };
    static template = "web.ClockMenu";
    static props = {};

    setup() {
        this.state = useState({
            time: "",
            date: "",
            open: false,
        });

        // Update time every second
        let timer = null;
        onWillStart(() => {
            this._updateClock();
        });

        onMounted(() => {
            timer = setInterval(() => this._updateClock(), 1000);
        });

        onWillUnmount(() => {
            clearInterval(timer);
        });
    }

    _updateClock() {
        const now = new Date();

        this.state.time = now.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });

        this.state.date = now.toLocaleDateString([], {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric",
        });
    }

    toggleMenu(ev) {
        ev.stopPropagation();
        this.state.open = !this.state.open;
    }
}

export const systrayItem = {
    Component: ClockMenu,
};

registry.category("systray").add("web.clock_menu", systrayItem, {
    sequence: 10,
});