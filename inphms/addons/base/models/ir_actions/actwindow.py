from __future__ import annotations

from inphms.orm import models, fields, api
from inphms import tools
from inphms.tools._vendor.safe_eval import safe_eval
from inphms.exceptions import ValidationError


class IrActionsAct_Window(models.Model):
    _name = 'ir.actions.act_window'
    _description = 'Action Window'
    _table = 'ir_act_window'
    _inherit = ['ir.actions.actions']
    _order = 'name, id'
    _allow_sudo_commands = False

    @api.constrains('res_model', 'binding_model_id')
    def _check_model(self):
        for action in self:
            if action.res_model not in self.env:
                raise ValidationError('Invalid model name “%s” in action definition.', action.res_model)
            if action.binding_model_id and action.binding_model_id.model not in self.env:
                raise ValidationError('Invalid model name “%s” in action definition.', action.binding_model_id.model)

    @api.depends('view_ids.view_mode', 'view_mode', 'view_id.type')
    def _compute_views(self):
        """ Compute an ordered list of the specific view modes that should be
            enabled when displaying the result of this action, along with the
            ID of the specific view to use for each mode, if any were required.

            This function hides the logic of determining the precedence between
            the view_modes string, the view_ids o2m, and the view_id m2o that
            can be set on the action.
        """
        for act in self:
            act.views = [(view.view_id.id, view.view_mode) for view in act.view_ids]
            got_modes = [view.view_mode for view in act.view_ids]
            all_modes = act.view_mode.split(',')
            missing_modes = [mode for mode in all_modes if mode not in got_modes]
            if missing_modes:
                if act.view_id.type in missing_modes:
                    # reorder missing modes to put view_id first if present
                    missing_modes.remove(act.view_id.type)
                    act.views.append((act.view_id.id, act.view_id.type))
                act.views.extend([(False, mode) for mode in missing_modes])

    @api.constrains('view_mode')
    def _check_view_mode(self):
        for rec in self:
            modes = rec.view_mode.split(',')
            if len(modes) != len(set(modes)):
                raise ValidationError('The modes in view_mode must not be duplicated: %s', modes)
            if ' ' in modes:
                raise ValidationError('No spaces allowed in view_mode: “%s”', modes)

    type = fields.Char(default="ir.actions.act_window")
    view_id = fields.Many2one('ir.ui.view', string='View Ref.', ondelete='set null')
    domain = fields.Char(string='Domain Value',
                         help="Optional domain filtering of the destination data, as a Python expression")
    context = fields.Char(string='Context Value', default={}, required=True,
                          help="Context dictionary as Python expression, empty by default (Default: {})")
    res_id = fields.Integer(string='Record ID', help="Database ID of record to open in form view, when ``view_mode`` is set to 'form' only")
    res_model = fields.Char(string='Destination Model', required=True,
                            help="Model name of the object to open in the view window")
    target = fields.Selection([('current', 'Current Window'), ('new', 'New Window'), ('fullscreen', 'Full Screen'), ('main', 'Main action of Current Window')], default="current", string='Target Window')
    view_mode = fields.Char(required=True, default='list,form',
                            help="Comma-separated list of allowed view modes, such as 'form', 'list', 'calendar', etc. (Default: list,form)")
    mobile_view_mode = fields.Char(default="kanban", help="First view mode in mobile and small screen environments (default='kanban'). If it can't be found among available view modes, the same mode as for wider screens is used)")
    usage = fields.Char(string='Action Usage',
                        help="Used to filter menu and home actions from the user form.")
    view_ids = fields.One2many('ir.actions.act_window.view', 'act_window_id', string='No of Views')
    views = fields.Binary(compute='_compute_views',
                          help="This function field computes the ordered list of views that should be enabled " \
                               "when displaying the result of an action, federating view mode, views and " \
                               "reference view. The result is returned as an ordered list of pairs (view_id,view_mode).")
    limit = fields.Integer(default=80, help='Default limit for the list view')
    group_ids = fields.Many2many('res.groups', 'ir_act_window_group_rel',
                                 'act_id', 'gid', string='Groups')
    search_view_id = fields.Many2one('ir.ui.view', string='Search View Ref.')
    embedded_action_ids = fields.One2many('ir.embedded.actions', compute="_compute_embedded_actions")
    filter = fields.Boolean()
    cache = fields.Boolean(string="Data Caching", default=True, help="If enabled, this action will cache the related data used in list, Kanban and form views with the aim to increase the loading speed")

    def _compute_embedded_actions(self):
        embedded_actions = self.env["ir.embedded.actions"].search([('parent_action_id', 'in', self.ids)]).filtered(lambda x: x.is_visible)
        for action in self:
            action.embedded_action_ids = embedded_actions.filtered(lambda rec: rec.parent_action_id == action)

    def read(self, fields=None, load='_classic_read'):
        """ call the method get_empty_list_help of the model and set the window action help message
        """
        result = super().read(fields, load=load)
        if not fields or 'help' in fields:
            for values in result:
                model = values.get('res_model')
                if model in self.env:
                    eval_ctx = dict(self.env.context)
                    try:
                        ctx = safe_eval(values.get('context', '{}'), eval_ctx)
                    except:
                        ctx = {}
                    values['help'] = self.with_context(**ctx).env[model].get_empty_list_help(values.get('help', ''))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        self.env.registry.clear_cache()
        for vals in vals_list:
            if not vals.get('name') and vals.get('res_model'):
                vals['name'] = self.env[vals['res_model']]._description
        return super().create(vals_list)

    def unlink(self):
        self.env.registry.clear_cache()
        return super().unlink()

    def exists(self):
        ids = self._existing()
        existing = self.filtered(lambda rec: rec.id in ids)
        return existing

    @api.model
    @tools.ormcache()
    def _existing(self):
        self.env.cr.execute("SELECT id FROM %s" % self._table)
        return {row[0] for row in self.env.cr.fetchall()}

    def _get_readable_fields(self):
        return super()._get_readable_fields() | {
            "context", "cache", "mobile_view_mode", "domain", "filter", "group_ids", "limit",
            "res_id", "res_model", "search_view_id", "target", "view_id", "view_mode", "views", "embedded_action_ids",
            # this is used by frontend, with the document layout wizard before send and print
            "close_on_report_download",
        }

    def _get_action_dict(self):
        """ Override to return action content with detailed embedded actions data if available.

            :return: A dict with updated action dictionary including embedded actions information.
        """
        result = super()._get_action_dict()
        if embedded_action_ids := result["embedded_action_ids"]:
            EmbeddedActions = self.env["ir.embedded.actions"]
            embedded_fields = EmbeddedActions._get_readable_fields()
            result["embedded_action_ids"] = EmbeddedActions.browse(embedded_action_ids).read(embedded_fields)
        return result
