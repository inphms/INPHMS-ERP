# ruff: noqa

from .response import Response
from .http import root, dispatch_rpc, content_disposition
from .serverclass import ThreadedServer, CommonServer
from .httprequest import HTTPRequest
from .controller import Controller
from .dispatchers import _dispatchers, Dispatcher
from .routing import route


import werkzeug.exceptions
from werkzeug.exceptions import (
    HTTPException)

## WERZEKUG PATCH
__wz_get_response = HTTPException.get_response
def get_response(self, environ=None, scope=None):
    return Response(__wz_get_response(self, environ, scope))
HTTPException.get_response = get_response # type: ignore

werkzeug_abort = werkzeug.exceptions.abort
def abort(status, *args, **kwargs):
    if isinstance(status, Response):
        status = status._wrapped__
    werkzeug_abort(status, *args, **kwargs)
werkzeug.exceptions.abort = abort


