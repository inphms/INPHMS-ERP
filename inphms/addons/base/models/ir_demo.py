from __future__ import annotations

from inphms.orm import models
from inphms.addons.base.models.ir_module.utils import assert_log_admin_access

class IrDemo(models.TransientModel):
    _name = 'ir.demo'
    _description = 'Demo'

    @assert_log_admin_access
    def install_demo(self):
        import inphms.modules.loading  # noqa: PLC0415
        inphms.modules.loading.force_demo(self.env)
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': '/inphms',
        }
