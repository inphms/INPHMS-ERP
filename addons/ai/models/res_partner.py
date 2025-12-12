from __future__ import annotations

from inphms.orm import fields, models, api


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner']

    agent_ids = fields.One2many('ai.agent', "partner_id", "Agent", store=True)

    @api.depends("user_ids.manual_im_status", "user_ids.presence_ids.status")
    def _compute_im_status(self):
        super()._compute_im_status()
        for partner in self:
            print(partner.name)
            if partner.agent_ids:
                partner.im_status = 'agent'