from __future__ import annotations

from inphms.orm import models, fields


class ResPartner(models.Model):
    _inherit = "res.partner"

    image_medium = fields.Binary(string="Medium-sized image", related="avatar_128")