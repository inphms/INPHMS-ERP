from __future__ import annotations

from inphms.orm import models, fields


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    customize_show = fields.Boolean("Show As Optional Inherit", default=False)
