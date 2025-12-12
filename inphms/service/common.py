from __future__ import annotations
import logging

from inphms import release
from inphms.modules import Registry, Environment
from inphms.exceptions import AccessDenied
from inphms.tools import _


_logger = logging.getLogger(__name__)

RPC_VERSION_1 = {
        'server_version': release.VERSION,
        'server_version_info': release.VERSION_INFO,
        'server_serie': release.SERIE,
        'protocol_version': 1,
}

def exp_login(db, login, password):
    return exp_authenticate(db, login, password, None)

def exp_authenticate(db, login, password, user_agent_env):
    if not user_agent_env:
        user_agent_env = {}
    with Registry(db).cursor() as cr:
        env = Environment(cr, None, {})
        env.transaction.default_env = env  # force default_env
        try:
            credential = {'login': login, 'password': password, 'type': 'password'}
            return env['res.users'].authenticate(credential, {**user_agent_env, 'interactive': False})['uid']
        except AccessDenied:
            return False

def exp_version():
    return RPC_VERSION_1

def exp_about(extended=False):
    """Return information about the Inphms Server.

    @param extended: if True then return version info
    @return string if extended is False else tuple
    """

    info = _('See http://inphms.com')

    if extended:
        return info, release.VERSION
    return info

def exp_set_loglevel(loglevel, logger=None):
    # TODO Previously, the level was set on the now deprecated
    # `inphms.netsvc.Logger` class.
    return True


def dispatch(method, params):
    g = globals()
    exp_method_name = 'exp_' + method
    if exp_method_name in g:
        return g[exp_method_name](*params)
    else:
        raise Exception("Method not found: %s" % method)
