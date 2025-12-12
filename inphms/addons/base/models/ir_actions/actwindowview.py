from __future__ import annotations

from inphms.orm import models, fields
from .utils import VIEW_TYPES

class IrActionsAct_WindowView(models.Model):
    _name = 'ir.actions.act_window.view'
    _description = 'Action Window View'
    _table = 'ir_act_window_view'
    _rec_name = 'view_id'
    _order = 'sequence,id'
    _allow_sudo_commands = False

    _unique_mode_per_action = models.UniqueIndex('(act_window_id, view_mode)')

    sequence = fields.Integer()
    view_id = fields.Many2one('ir.ui.view', string='View')
    view_mode = fields.Selection(VIEW_TYPES, string='View Type', required=True)
    act_window_id = fields.Many2one('ir.actions.act_window', string='Action', ondelete='cascade', index='btree_not_null')
    multi = fields.Boolean(string='On Multiple Doc.', help="If set to true, the action will not be displayed on the right toolbar of a form view.")


class IrActionsAct_Window_Close(models.Model):
    _name = 'ir.actions.act_window_close'
    _description = 'Action Window Close'
    _inherit = ['ir.actions.actions']
    _table = 'ir_actions'
    _allow_sudo_commands = False

    type = fields.Char(default='ir.actions.act_window_close')

    def _get_readable_fields(self):
        return super()._get_readable_fields() | {
            # 'effect' and 'infos' are not real fields of `ir.actions.act_window_close` but they are
            # used to display the rainbowman ('effect') and waited by the action_service ('infos').
            "effect", "infos"
        }
