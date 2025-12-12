from __future__ import annotations

from inphms import tools
from inphms.databases import SQL
from inphms.exceptions import AccessError
from inphms.orm import models, fields, api
from .model import _logger
from .utils import ACCESS_ERROR_GROUPS, ACCESS_ERROR_HEADER, ACCESS_ERROR_NOGROUP, ACCESS_ERROR_RESOLUTION


class IrModelAccess(models.Model):
    _name = 'ir.model.access'
    _description = 'Model Access'
    _order = 'model_id,group_id,name,id'
    _allow_sudo_commands = False

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True, help='If you uncheck the active field, it will disable the ACL without deleting it (if you delete a native ACL, it will be re-created when you reload the module).')
    model_id = fields.Many2one('ir.model', string='Model', required=True, index=True, ondelete='cascade')
    group_id = fields.Many2one('res.groups', string='Group', ondelete='restrict', index=True)
    perm_read = fields.Boolean(string='Read Access')
    perm_write = fields.Boolean(string='Write Access')
    perm_create = fields.Boolean(string='Create Access')
    perm_unlink = fields.Boolean(string='Delete Access')

    @api.model
    def group_names_with_access(self, model_name, access_mode):
        """ Return the names of visible groups which have been granted
            ``access_mode`` on the model ``model_name``.

           :rtype: list
        """
        assert access_mode in ('read', 'write', 'create', 'unlink'), 'Invalid access mode'
        lang = self.env.lang or 'en_US'
        self.env.cr.execute(f"""
            SELECT COALESCE(c.name->>%s, c.name->>'en_US'), COALESCE(g.name->>%s, g.name->>'en_US')
              FROM ir_model_access a
              JOIN ir_model m ON (a.model_id = m.id)
              JOIN res_groups g ON (a.group_id = g.id)
         LEFT JOIN res_groups_privilege c ON (c.id = g.privilege_id)
             WHERE m.model = %s
               AND a.active = TRUE
               AND a.perm_{access_mode} = TRUE
          ORDER BY c.name, g.name NULLS LAST
        """, [lang, lang, model_name])
        return [('%s/%s' % x) if x[0] else x[1] for x in self.env.cr.fetchall()]

    @api.model
    @tools.ormcache('model_name', 'access_mode', cache='stable')
    def _get_access_groups(self, model_name, access_mode='read'):
        """ Return the group expression object that represents the users who
        have ``access_mode`` to the model ``model_name``.
        """
        assert access_mode in ('read', 'write', 'create', 'unlink'), 'Invalid access mode'
        model = self.env['ir.model']._get(model_name)
        accesses = self.sudo().search([
            (f'perm_{access_mode}', '=', True), ('model_id', '=', model.id),
        ])

        group_definitions = self.env['res.groups']._get_group_definitions()
        if not accesses:
            return group_definitions.empty
        if not all(access.group_id for access in accesses):  # there is some global access
            return group_definitions.universe
        return group_definitions.from_ids(accesses.group_id.ids)

    # The context parameter is useful when the method translates error messages.
    # But as the method raises an exception in that case,  the key 'lang' might
    # not be really necessary as a cache key, unless the `ormcache`
    # decorator catches the exception (it does not at the moment.)

    @tools.ormcache('self.env.uid', 'mode')
    def _get_allowed_models(self, mode='read'):
        assert mode in ('read', 'write', 'create', 'unlink'), 'Invalid access mode'

        group_ids = self.env.user._get_group_ids()
        self.flush_model()
        rows = self.env.execute_query(SQL("""
            SELECT m.model
              FROM ir_model_access a
              JOIN ir_model m ON (m.id = a.model_id)
             WHERE a.perm_%s
               AND a.active
               AND (
                    a.group_id IS NULL OR
                    a.group_id IN %s
                )
            GROUP BY m.model
        """, SQL(mode), tuple(group_ids) or (None,)))

        return frozenset(v[0] for v in rows)

    @api.model
    def check(self, model, mode='read', raise_exception=True):
        if self.env.su:
            # User root have all accesses
            return True

        assert isinstance(model, str), 'Not a model name: %s' % (model,)

        if model not in self.env:
            _logger.error('Missing model %s', model)

        has_access = model in self._get_allowed_models(mode)
        if not has_access and raise_exception:
            raise self._make_access_error(model, mode) from None
        return has_access

    def _make_access_error(self, model: str, mode: str):
        """ Return the exception corresponding to an access error. """
        _logger.info('Access Denied by ACLs for operation: %s, uid: %s, model: %s', mode, self.env.uid, model)

        operation_error = str(ACCESS_ERROR_HEADER[mode]) % {
            'document_kind': self.env['ir.model']._get(model).name or model,
            'document_model': model,
        }

        groups = "\n".join(f"\t- {g}" for g in self.group_names_with_access(model, mode))
        if groups:
            group_info = str(ACCESS_ERROR_GROUPS) % {'groups_list': groups}
        else:
            group_info = str(ACCESS_ERROR_NOGROUP)

        resolution_info = str(ACCESS_ERROR_RESOLUTION)

        return AccessError(operation_error + "\n\n" + group_info + "\n\n" + resolution_info)

    @api.model
    def call_cache_clearing_methods(self):
        self.env.invalidate_all()
        self.env.registry.clear_cache('stable')  # mainly _get_allowed_models

    #
    # Check rights on actions
    #
    @api.model_create_multi
    def create(self, vals_list):
        self.call_cache_clearing_methods()
        for ima in vals_list:
            if "group_id" in ima and not ima["group_id"] and any([
                    ima.get("perm_read"),
                    ima.get("perm_write"),
                    ima.get("perm_create"),
                    ima.get("perm_unlink")]):
                _logger.warning("Rule %s has no group, this is a deprecated feature. Every access-granting rule should specify a group.", ima['name'])
        return super().create(vals_list)

    def write(self, vals):
        self.call_cache_clearing_methods()
        return super().write(vals)

    def unlink(self):
        self.call_cache_clearing_methods()
        return super().unlink()
