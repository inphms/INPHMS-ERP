from __future__ import annotations

from inphms.addons.bus.controllers.websocket import WebsocketController
from inphms.server.utils import request
from inphms.server import route
from inphms.exceptions import SessionExpiredException


class WebsocketControllerPresence(WebsocketController):
    """Override of websocket controller to add mail features (presence in particular)."""

    @route("/websocket/update_bus_presence", type="jsonrpc", auth="public", cors="*")
    def update_bus_presence(self, inactivity_period):
        """Manually update presence of current user, useful when implementing custom websocket code.
        This is mainly used by Inphms.sh."""
        if "is_websocket_session" not in request.session:
            raise SessionExpiredException()
        request.env["ir.websocket"]._update_mail_presence(int(inactivity_period))
        return {}
