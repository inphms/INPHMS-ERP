from __future__ import annotations

from inphms.server.utils import request
from inphms.orm.fields import Domain
from inphms.orm import api, models, fields


SKIP_CAPTCHA_LOGIN = object()


class ResUsers(models.Model):
    _inherit = "res.users"

    color_scheme = fields.Selection(string="Color Scheme", store=False, related="res_users_settings_id.color_scheme", readonly=False)

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        # if we have a search with a limit, move current user as the first result
        domain = Domain(domain or Domain.TRUE)
        user_list = super().name_search(name, domain, operator, limit)
        uid = self.env.uid
        # index 0 is correct not Falsy in this case, use None to avoid ignoring it
        if (index := next((i for i, (user_id, _name) in enumerate(user_list) if user_id == uid), None)) is not None:
            # move found user first
            user_tuple = user_list.pop(index)
            user_list.insert(0, user_tuple)
        elif limit is not None and len(user_list) == limit:
            # user not found and limit reached, try to find the user again
            if user_tuple := super().name_search(name, domain & Domain('id', '=', uid), operator, limit=1):
                user_list = [user_tuple[0], *user_list[:-1]]
        return user_list

    def _on_webclient_bootstrap(self):
        self.ensure_one()

    def _should_captcha_login(self, credential):
        if request and request.env.context.get('skip_captcha_login') is SKIP_CAPTCHA_LOGIN:
            return False
        return credential['type'] == 'password'

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "color_scheme",
        ]
        
    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            "color_scheme",
        ]