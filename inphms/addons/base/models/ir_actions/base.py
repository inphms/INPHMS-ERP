from __future__ import annotations
import base64
import re

from collections import defaultdict
from pytz import timezone

from inphms.tools import frozendict, float_compare, _
from inphms.exceptions import MissingError, ValidationError
from inphms.orm.fields import Command
from inphms.orm import models, api, fields
from inphms import tools
from inphms.tools._vendor.safe_eval import datetime as _sfdatetime, dateutil as _sfdateutil, time as _sftime


class IrActionsActions(models.Model):
    _name = 'ir.actions.actions'
    _description = 'Actions'
    _table = 'ir_actions'
    _order = 'name, id'
    _allow_sudo_commands = False

    _path_unique = models.Constraint(
        'unique(path)',
        "Path to show in the URL must be unique! Please choose another one.",
    )

    name = fields.Char(string='Action Name', required=True, translate=True)
    type = fields.Char(string='Action Type', required=True)
    xml_id = fields.Char(compute='_compute_xml_id', string="External ID")
    path = fields.Char(string="Path to show in the URL")
    help = fields.Html(string='Action Description',
                       help='Optional help text for the users with a description of the target view, such as its usage and purpose.',
                       translate=True)
    binding_model_id = fields.Many2one('ir.model', ondelete='cascade',
                                       help="Setting a value makes this action available in the sidebar for the given model.")
    binding_type = fields.Selection([('action', 'Action'),
                                     ('report', 'Report')],
                                    required=True, default='action')
    binding_view_types = fields.Char(default='list,form')

    @api.constrains('path')
    def _check_path(self):
        for action in self:
            if action.path:
                if not re.fullmatch(r'[a-z][a-z0-9_-]*', action.path):
                    raise ValidationError(_('The path should contain only lowercase alphanumeric characters, underscore, and dash, and it should start with a letter.'))
                if action.path.startswith("m-"):
                    raise ValidationError(_("'m-' is a reserved prefix."))
                if action.path.startswith("action-"):
                    raise ValidationError(_("'action-' is a reserved prefix."))
                if action.path == "new":
                    raise ValidationError(_("'new' is reserved, and can not be used as path."))
                # Tables ir_act_window, ir_act_report_xml, ir_act_url, ir_act_server and ir_act_client
                # inherit from table ir_actions (see base_data.sql). The path must be unique across
                # all these tables. The unique constraint is not enough because a big limitation of
                # the inheritance feature is that unique indexes only apply to single tables, and
                # not accross all the tables. So we need to check the uniqueness of the path manually.
                # For more information, see: https://www.postgresql.org/docs/14/ddl-inherit.html#DDL-INHERIT-CAVEATS

                # Note that, we leave the unique constraint in place to check the uniqueness of the path
                # within the same table before checking the uniqueness across all the tables.
                if (self.env['ir.actions.actions'].search_count([('path', '=', action.path)]) > 1):
                    raise ValidationError(_("Path to show in the URL must be unique! Please choose another one."))

    def _compute_xml_id(self):
        res = self.get_external_id()
        for record in self:
            record.xml_id = res.get(record.id)

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        # self.get_bindings() depends on action records
        self.env.registry.clear_cache()
        return res

    def write(self, vals):
        res = super().write(vals)
        # self.get_bindings() depends on action records
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        """unlink ir.action.todo/ir.filters which are related to actions which will be deleted.
           NOTE: ondelete cascade will not work on ir.actions.actions so we will need to do it manually."""
        todos = self.env['ir.actions.todo'].search([('action_id', 'in', self.ids)])
        todos.unlink()
        filters = self.env['ir.filters'].search([('action_id', 'in', self.ids)])
        filters.unlink()
        res = super().unlink()
        # self.get_bindings() depends on action records
        self.env.registry.clear_cache()
        return res

    @api.ondelete(at_uninstall=True)
    def _unlink_check_home_action(self):
        self.env['res.users'].with_context(active_test=False).search([('action_id', 'in', self.ids)]).sudo().write({'action_id': None})

    @api.model
    def _get_eval_context(self, action=None):
        """ evaluation context to pass to safe_eval """
        return {
            'uid': self.env.uid,
            'user': self.env.user,
            'time': _sftime,
            'datetime': _sfdatetime,
            'dateutil': _sfdateutil,
            'timezone': timezone,
            'float_compare': float_compare,
            'b64encode': base64.b64encode,
            'b64decode': base64.b64decode,
            'Command': Command,
        }

    @api.model
    def get_bindings(self, model_name):
        """ Retrieve the list of actions bound to the given model.

           :return: a dict mapping binding types to a list of dict describing
                    actions, where the latter is given by calling the method
                    ``read`` on the action record.
        """
        result = {}
        for action_type, all_actions in self._get_bindings(model_name).items():
            actions = []
            for action in all_actions:
                action = dict(action)
                groups = action.pop('group_ids', None)
                if groups and not any(self.env.user.has_group(ext_id) for ext_id in groups):
                    # the user may not perform this action
                    continue
                res_model = action.pop('res_model', None)
                if res_model and not self.env['ir.model.access'].check(
                    res_model,
                    mode='read',
                    raise_exception=False
                ):
                    # the user won't be able to read records
                    continue
                actions.append(action)
            if actions:
                result[action_type] = actions
        return result

    @tools.ormcache('model_name', 'self.env.lang')
    def _get_bindings(self, model_name):
        cr = self.env.cr

        # discard unauthorized actions, and read action definitions
        result = defaultdict(list)

        self.env.flush_all()
        cr.execute("""
            SELECT a.id, a.type, a.binding_type
              FROM ir_actions a
              JOIN ir_model m ON a.binding_model_id = m.id
             WHERE m.model = %s
          ORDER BY a.id
        """, [model_name])
        for action_id, action_model, binding_type in cr.fetchall():
            try:
                action = self.env[action_model].sudo().browse(action_id)
                fields = ['name', 'binding_view_types']
                for field in ('group_ids', 'res_model', 'sequence', 'domain'):
                    if field in action._fields:
                        fields.append(field)
                action = action.read(fields)[0]
                if action.get('group_ids'):
                    # transform the list of ids into a list of xml ids
                    groups = self.env['res.groups'].browse(action['group_ids'])
                    action['group_ids'] = list(groups._ensure_xml_id().values())
                if 'domain' in action and not action.get('domain'):
                    action.pop('domain')
                result[binding_type].append(frozendict(action))
            except (MissingError):
                continue

        # sort actions by their sequence if sequence available
        if result.get('action'):
            result['action'] = tuple(sorted(result['action'], key=lambda vals: vals.get('sequence', 0)))
        return frozendict(result)

    @api.model
    def _for_xml_id(self, full_xml_id):
        """ Returns the action content for the provided xml_id

        :param full_xml_id: the namespace-less id of the action (the @id
            attribute from the XML file)
        :return: A read() view of the ir.actions.action safe for web use
        """
        record = self.env.ref(full_xml_id)
        assert isinstance(self.env[record._name], self.env.registry[self._name])
        return record._get_action_dict()

    def _get_action_dict(self):
        """ Returns the action content for the provided action record.
        """
        self.ensure_one()
        readable_fields = self._get_readable_fields()
        return {
            field: value
            for field, value in self.sudo().read()[0].items()
            if field in readable_fields
        }

    def _get_readable_fields(self):
        """ return the list of fields that are safe to read

        Fetched via /web/action/load or _for_xml_id method
        Only fields used by the web client should included
        Accessing content useful for the server-side must
        be done manually with superuser
        """
        return {
            "binding_model_id", "binding_type", "binding_view_types",
            "display_name", "help", "id", "name", "type", "xml_id",
            "path",
        }
