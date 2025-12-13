from __future__ import annotations
import logging

from inphms.orm import models, fields


_logger = logging.getLogger(__name__)


class IrActionsWorkspace(models.Model):
    _name="ir.actions.workspace"
    _description="Workspace Action"
    _inherit=["ir.actions.actions"]

    type= fields.Char(default="ir.actions.workspace")

    context = fields.Char(string='Context Value', default={}, required=True,
                          help="Context dictionary as Python expression, empty by default (Default: {})")

    target = fields.Selection([('current', 'Current Window'), ('new', 'New Window'), ('fullscreen', 'Full Screen'), ('main', 'Main action of Current Window')], default="current", string='Target Window')


class IrUiMenu(models.Model):
    _inherit="ir.ui.menu"

    action = fields.Reference(
        selection_add=[
            ('ir.actions.workspace', 'ir.actions.workspace')
        ],
        ondelete={'ir.actions.workspace': 'cascade'}
    )
