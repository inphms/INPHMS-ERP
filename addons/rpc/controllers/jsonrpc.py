from __future__ import annotations
import logging

from inphms.server import Controller, route, dispatch_rpc
from . import RPC_DEPRECATION_NOTICE, _check_request

_logger = logging.getLogger(__name__)


class JSONRPC(Controller):
    @route('/jsonrpc', type='jsonrpc', auth="none", save_session=False)
    def jsonrpc(self, service, method, args):
        """ Method used by client APIs to contact OpenERP. """
        _logger.warning(RPC_DEPRECATION_NOTICE, __name__)
        _check_request()
        return dispatch_rpc(service, method, args)
