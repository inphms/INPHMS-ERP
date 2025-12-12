from __future__ import annotations

from werkzeug.exceptions import NotFound

from inphms.server.utils import request
from inphms.server import route
from ..tools.discuss import add_guest_to_context, Store
from .thread import ThreadController


class MessageReactionController(ThreadController):
    @route("/mail/message/reaction", methods=["POST"], type="jsonrpc", auth="public")
    @add_guest_to_context
    def mail_message_reaction(self, message_id, content, action, **kwargs):
        message = self._get_message_with_access(int(message_id), mode="create", **kwargs)
        if not message:
            raise NotFound()
        partner, guest = self._get_reaction_author(message, **kwargs)
        if not partner and not guest:
            raise NotFound()
        store = Store()
        # sudo: mail.message - access mail.message.reaction through an accessible message is allowed
        message.sudo()._message_reaction(content, action, partner, guest, store)
        return store.get_result()

    def _get_reaction_author(self, message, **kwargs):
        return request.env["res.partner"]._get_current_persona()
