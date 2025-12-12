# ruff : noqa

from . import json2


RPC_DEPRECATION_NOTICE = """\
The /xmlrpc, /xmlrpc/2 and /jsonrpc endpoints are deprecated in Inphms \
and scheduled for removal in Inphms 1. Please report the problem to the \
client making the request.
Mute this logger: --log-handler %s:ERROR
https://www.inphms.com/documentation/latest/developer/reference/external_api.html#migrating-from-xml-rpc-json-rpc"""


def _check_request():
    if request.db:
        request.env.cr.close()


from inphms import release
from inphms.server.utils import request
from inphms.server import route

from .jsonrpc import JSONRPC
from .xmlrpc import XMLRPC

class RPC(XMLRPC, JSONRPC):
    @route(['/web/version', '/json/version'], type='http', auth='none', readonly=True)
    def version(self):
        return request.make_json_response({
            'version_info': release.VERSION_INFO,
            'version': release.VERSION,
        })