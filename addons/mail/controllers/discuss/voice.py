from __future__ import annotations

from inphms.server import Controller, route
from inphms.server.utils import request
from inphms.tools import file_open


class VoiceController(Controller):

    @route("/discuss/voice/worklet_processor", methods=["GET"], type="http", auth="public", readonly=True)
    def voice_worklet_processor(self):
        with file_open("mail/static/src/discuss/voice_message/worklets/processor.js", "rb") as f:
            data = f.read()
        return request.make_response(
            data,
            headers=[
                ("Content-Type", "application/javascript"),
            ],

        )