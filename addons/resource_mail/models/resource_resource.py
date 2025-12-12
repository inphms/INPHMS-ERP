from __future__ import annotations

from random import randint

from inphms.orm import fields, models


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    def _default_color(self):
        return randint(1, 11)

    color = fields.Integer(default=_default_color)
    im_status = fields.Char(related='user_id.im_status')

    def get_avatar_card_data(self, fields):
        return self.env['resource.resource'].search_read(
            domain=[('id', 'in', self.ids)],
        )
