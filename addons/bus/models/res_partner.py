from __future__ import annotations

from inphms.orm import models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "bus.listener.mixin"]
