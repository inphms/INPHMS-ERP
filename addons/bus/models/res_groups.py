from __future__ import annotations

from inphms.orm import models


class ResGroups(models.Model):
    _name = 'res.groups'
    _inherit = ["res.groups", "bus.listener.mixin"]
