from __future__ import annotations

from inphms.orm import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super(IrHttp, self).session_info()
        if self.env.user._is_internal():
            result['show_effect'] = bool(self.env['ir.config_parameter'].sudo().get_param('base_setup.show_effect'))
        return result
