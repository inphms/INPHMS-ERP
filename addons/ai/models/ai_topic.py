from __future__ import annotations

from inphms.orm import models, fields, api

class AITopic(models.Model):
    _name = "ai.topic"
    _description = "Create a topic that leverages instructions and tools to direct Inphms AI in assisting the user with their tasks."
    _rec_name = 'name'

    description = fields.Text("Description", store=True)
    instructions = fields.Text("Instruction", store=True)

    name = fields.Char("Title", required=True, store=True)
    tool_ids = fields.Many2many("ir.actions.server", relation="ai_topic_ir_act_server_rel",
                                 column1="ai_topic_id", column2="ir_act_server_id",
                                 store=True)
