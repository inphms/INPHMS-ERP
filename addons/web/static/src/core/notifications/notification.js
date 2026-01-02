import { Component, useRef, onMounted } from "@inphms/owl";

const AUTOCLOSE_DELAY = 4000;
const NOTIFICATION_ICONS = {
    warning: 'M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z',
    danger: 'M8 16A8 8 0 108 0 8 8 0 008 16M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707 5.354 11.354a.5.5 0 11-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708',
    success: 'M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zm-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z',
    info: 'M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm.93-9.412-1 4.705c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287zM8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2z',
}
const UNKNOWN_ICON = 'M5.255 5.786a.237.237 0 00.241.247h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 00.25.246h.811a.25.25 0 00.25-.25V9.283c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.267 0-2.655.59-2.75 2.286Zm1.557 5.763c0 .533.425.927 1.01.927.609 0 1.028-.394 1.028-.927 0-.552-.42-.94-1.029-.94-.584 0-1.009.388-1.009.94ZM8 16A8 8 0 018 0 8 8 0 118 16Z'

export class Notification extends Component {
    static template = "web.NotificationWowl";
    static props = {
        message: {
            validate: (m) =>
                typeof m === "string" ||
                (typeof m === "object" && typeof m.toString === "function"),
        },
        type: {
            type: String,
            optional: true,
            validate: (t) => ["warning", "danger", "success", "info"].includes(t),
        },
        title: { type: [String, Boolean, { toString: Function }], optional: true },
        className: { type: String, optional: true },
        buttons: {
            type: Array,
            element: {
                type: Object,
                shape: {
                    name: { type: String },
                    icon: { type: String, optional: true },
                    primary: { type: Boolean, optional: true },
                    onClick: Function,
                },
            },
            optional: true,
        },
        sticky: { type: Boolean, optional: true },
        autocloseDelay: { type: Number, optional: true },
        close: { type: Function },
    };
    static defaultProps = {
        buttons: [],
        className: "",
        type: "warning",
        autocloseDelay: AUTOCLOSE_DELAY,
    };
    setup() {
        this.autocloseProgress = useRef("autoclose_progress_bar");
        this.iconPaths = NOTIFICATION_ICONS[this.props.type] || UNKNOWN_ICON;
        onMounted(() => this.startNotificationTimer());
    }

    freeze() {
        this.startedTimestamp = false;
        this.autocloseProgress.el.style.width = 0;
    }

    refresh() {
        this.startNotificationTimer();
    }

    close() {
        this.props.close();
    }

    startNotificationTimer() {
        if (this.props.sticky) {
            return;
        }
        this.startedTimestamp = luxon.DateTime.now().ts;

        const cb = () => {
            if (this.startedTimestamp) {
                const currentProgress =
                    (luxon.DateTime.now().ts - this.startedTimestamp) / this.props.autocloseDelay;
                if (currentProgress > 1) {
                    this.close();
                    return;
                }
                if (this.autocloseProgress.el) {
                    this.autocloseProgress.el.style.width = `${(1 - currentProgress) * 100}%`;
                }
                requestAnimationFrame(cb);
            }
        };
        cb();
    }
}
