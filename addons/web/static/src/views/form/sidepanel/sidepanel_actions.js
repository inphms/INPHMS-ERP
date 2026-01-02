import { Component } from "@inphms/owl";

// Used for compiling <sidepanel> tag

export class SidePanelActions extends Component {
    static template = "web.SidePanelActions";
    static components = {};
    static props = {
        slots: Object,
        class: { type: String, optional: 1 },
    };

    setup() {}
}
