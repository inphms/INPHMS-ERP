from __future__ import annotations

from inphms.orm import fields, models


class IrActionsAct_Url(models.Model):
    _name = 'ir.actions.act_url'
    _description = 'Action URL'
    _table = 'ir_act_url'
    _inherit = ['ir.actions.actions']
    _order = 'name, id'
    _allow_sudo_commands = False

    type = fields.Char(default='ir.actions.act_url')
    url = fields.Text(string='Action URL', required=True)
    target = fields.Selection([('new', 'New Window'), ('self', 'This Window'), ('download', 'Download')],
                              string='Action Target', default='new', required=True)

    def _get_readable_fields(self):
        return super()._get_readable_fields() | {
            "target", "url", "close",
        }
