from __future__ import annotations

from inphms.orm import models, fields, api

class AIAgentSources(models.Model):
    _name = "ai.agent.sources"

    agent_id = fields.Many2one("ai.agent", "Agent", store=True, required=True, index=True, ondelete="Restrict")
    attachment_id = fields.Many2one("ir.attachment", "Attachment", store=True, index=True, ondelete="Cascade")
    error_details = fields.Text("Error Detailes", store=True, readonly=True)
    file_size = fields.Integer("File Size", related="attachment_id.file_size")
    is_active = fields.Boolean("Active", store=True, help="If the source is active, it will be used in the RAG context.")
    mimetype = fields.Char("Mime Type", related="attachment_id.mimetype")
    status = fields.Selection([
        ('processing', 'Processing'),
        ('indexed', 'Indexed'),
        ('failed', 'Failed')
    ], "Status", store=True)
    type = fields.Selection([
        ('url', 'URL'), ('binary', 'File')
    ], "Type", readonly=True, store=True, required=True)
    url = fields.Char("URL", store=True)
    user_has_access = fields.Boolean("User Has Access", readonly=True, store=False)
