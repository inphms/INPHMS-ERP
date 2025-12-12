from __future__ import annotations
import json

from inphms.server import Controller, route
from inphms.server.utils import request


class BusController(Controller):
    @route('/bus/get_model_definitions', methods=['POST'], type='http', auth='user')
    def get_model_definitions(self, model_names_to_fetch, **kwargs):
        return request.make_response(json.dumps(
            request.env['ir.model']._get_model_definitions(json.loads(model_names_to_fetch)),
        ))

    @route("/bus/has_missed_notifications", type="jsonrpc", auth="public")
    def has_missed_notifications(self, last_notification_id):
        # sudo - bus.bus: checking if a notification still exists in order to
        # detect missed notification during disconnect is allowed.
        return request.env["bus.bus"].sudo().search_count([("id", "=", last_notification_id)]) == 0
