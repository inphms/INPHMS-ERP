from __future__ import annotations

from inphms.orm import fields, models


class ResPartnerIndustry(models.Model):
    _name = 'res.partner.industry'
    _description = 'Industry'
    _order = "name, id"

    name = fields.Char('Name', translate=True)
    full_name = fields.Char('Full Name', translate=True)
    active = fields.Boolean('Active', default=True)
