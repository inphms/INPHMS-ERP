from __future__ import annotations

from inphms.server.utils import request
from inphms.orm import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)

        # add signup token or login to the session if given
        for key in ('auth_signup_token', 'auth_login'):
            val = request.httprequest.args.get(key)
            if val is not None:
                request.session[key] = val
