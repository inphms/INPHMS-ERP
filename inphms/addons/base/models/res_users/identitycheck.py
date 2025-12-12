from __future__ import annotations
import json
import time

from inphms.tools import _
from .utils import request
from inphms.orm import fields, models
from inphms.orm.models.utils import NO_ACCESS
from inphms.exceptions import AccessDenied, UserError


class ResUsersIdentitycheck(models.TransientModel):
    """ Wizard used to re-check the user's credentials (password) and eventually
    revoke access to his account to every device he has an active session on.

    Might be useful before the more security-sensitive operations, users might be
    leaving their computer unlocked & unattended. Re-checking credentials mitigates
    some of the risk of a third party using such an unattended device to manipulate
    the account.
    """
    _name = 'res.users.identitycheck'
    _description = "Password Check Wizard"

    request = fields.Char(readonly=True, groups=NO_ACCESS)
    auth_method = fields.Selection([('password', 'Password')], default=lambda self: self._get_default_auth_method())
    password = fields.Char(store=False)

    def _get_default_auth_method(self):
        return 'password'

    def _check_identity(self):
        try:
            credential = {
                'login': self.env.user.login,
                'password': self.env.context.get('password'),
                'type': 'password',
            }
            self.create_uid._check_credentials(credential, {'interactive': True})
        except AccessDenied:
            raise UserError(_("Incorrect Password, try again or click on Forgot Password to reset your password."))

    def run_check(self):
        # The password must be in the context with the key name `'password'`
        assert request, "This method can only be accessed over HTTP"
        self._check_identity()

        request.session['identity-check-last'] = time.time()
        ctx, model, ids, method, args, kwargs = json.loads(self.sudo().request)
        method = getattr(self.env(context=ctx)[model].browse(ids), method)
        assert getattr(method, '__has_check_identity', False)
        return method(*args, **kwargs)
