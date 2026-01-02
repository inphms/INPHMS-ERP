import { Component, xml, onWillDestroy } from "@inphms/owl";
import { WebSidebar } from "../websidebar/websidebar";
import { useService } from "@web/core/utils/hooks";

// -----------------------------------------------------------------------------
// ActionContainer (Component)
// -----------------------------------------------------------------------------
export class ActionContainer extends Component {
    static components = {
        WebSidebar,
    };
    static props = {};
    static template = xml`
        <t t-name="web.ActionContainer">
          <div class="o_action_manager">
            <t t-if="!hm.hasHomeMenu">
                <WebSidebar/>
            </t>
            <t t-if="info.Component" t-component="info.Component" className="'o_action'" t-props="info.componentProps" t-key="info.id"/>
          </div>
        </t>`;

    setup() {
        this.info = {};
        this.hm = useService("home_menu");
        this.onActionManagerUpdate = ({ detail: info }) => {
            this.info = info;
            this.render();
        };
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE", this.onActionManagerUpdate);
        onWillDestroy(() => {
            this.env.bus.removeEventListener("ACTION_MANAGER:UPDATE", this.onActionManagerUpdate);
        });
    }
}
