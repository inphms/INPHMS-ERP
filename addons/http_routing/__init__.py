# ruffL noqa

from . import controllers
from . import models

from inphms.server.utils import request


def _post_init_hook(env):
    if request:
        request.is_frontend = False
        request.is_frontend_multilang = False
