from __future__ import annotations

from json import loads, dumps

from inphms.server import Controller, route
from inphms.server.utils import request


class Model(Controller):
    @route("/web/model/get_definitions", methods=["POST"], type="http", auth="user")
    def get_model_definitions(self, model_names, **kwargs):
        return request.make_response(
            dumps(
                request.env["ir.model"]._get_definitions(loads(model_names)),
            )
        )