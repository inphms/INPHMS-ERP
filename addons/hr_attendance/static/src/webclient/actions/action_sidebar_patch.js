import { patch } from "@web/core/utils/patch";
import { ActionSidebar } from "@web/webclient/actions/action_sidebar";

patch(ActionSidebar.prototype, {
    get isInAttendancesApp() {
        const attendanceMenu = this.menuService.getApps().filter(apps => apps.name === 'Attendances');
        const currentApp = this.menuService.getCurrentApp();
        return (currentApp && currentApp.id === attendanceMenu[0]?.id) && (!this.isInHomeMenu);
    },

    selectMenuAttendances() {
        if (this.isInAttendancesApp) return;
        const attendanceMenu = this.menuService.getApps().filter(apps => apps.name === 'Attendances');
        this.menuService.selectMenu(attendanceMenu[0]);
    }
});