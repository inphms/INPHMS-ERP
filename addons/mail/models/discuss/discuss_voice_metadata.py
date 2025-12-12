from __future__ import annotations

from inphms.orm import models, fields


class DiscussVoiceMetadata(models.Model):
    _name = 'discuss.voice.metadata'
    _description = "Metadata for voice attachments"

    attachment_id = fields.Many2one(
        "ir.attachment", ondelete="cascade", bypass_search_access=True, copy=False, index=True
    )
