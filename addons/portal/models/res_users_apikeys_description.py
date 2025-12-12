from __future__ import annotations

from inphms.orm import models
from inphms.tools import _
from inphms.exceptions import AccessError


class ResUsersApikeysDescription(models.TransientModel):
    _inherit = 'res.users.apikeys.description'

    def check_access_make_key(self):
        try:
            return super().check_access_make_key()
        except AccessError:
            if self.env['ir.config_parameter'].sudo().get_param('portal.allow_api_keys'):
                if self.env.user._is_portal():
                    return
                else:
                    raise AccessError(_("Only internal and portal users can create API keys"))
            raise
