from __future__ import annotations

from .utils import DEP_STATES
from inphms.orm import models, api, fields


class IrModuleModuleDependency(models.Model):
    _name = 'ir.module.module.dependency'
    _description = "Module dependency"
    _log_access = False  # inserts are done manually, create and write uid, dates are always null
    _allow_sudo_commands = False

    # the dependency name
    name = fields.Char(index=True)

    # the module that depends on it
    module_id = fields.Many2one('ir.module.module', 'Module', ondelete='cascade')

    # the module corresponding to the dependency, and its status
    depend_id = fields.Many2one('ir.module.module', 'Dependency',
                                compute='_compute_depend', search='_search_depend')
    state = fields.Selection(DEP_STATES, string='Status', compute='_compute_state')

    auto_install_required = fields.Boolean(
        default=True,
        help="Whether this dependency blocks automatic installation "
             "of the dependent")

    @api.depends('name')
    def _compute_depend(self):
        # retrieve all modules corresponding to the dependency names
        names = {dep.name for dep in self}
        mods = self.env['ir.module.module'].search([('name', 'in', names)])

        # index modules by name, and assign dependencies
        name_mod = {mod.name: mod for mod in mods}
        for dep in self:
            dep.depend_id = name_mod.get(dep.name)

    def _search_depend(self, operator, value):
        if operator not in ('in', 'any'):
            return NotImplemented
        modules = self.env['ir.module.module'].browse(value)
        return [('name', 'in', modules.mapped('name'))]

    @api.depends('depend_id.state')
    def _compute_state(self):
        for dependency in self:
            dependency.state = dependency.depend_id.state or 'unknown'

    @api.model
    def all_dependencies(self, module_names):
        to_search = {key: True for key in module_names}
        res = {}
        def search_direct_deps(to_search, res):
            to_search_list = to_search.keys()
            dependencies = self.web_search_read(domain=[("module_id.name", "in", to_search_list)], specification={"module_id":{"fields":{"name":{}}}, "name": {}, })["records"]
            to_search.clear()
            for dependency in dependencies:
                dep_name = dependency["name"]
                mod_name = dependency["module_id"]["name"]
                if dep_name not in res and dep_name not in to_search and dep_name not in to_search_list:
                    to_search[dep_name] = True
                if mod_name not in res:
                    res[mod_name] = []
                res[mod_name].append(dep_name)
        search_direct_deps(to_search, res)
        while to_search:
            search_direct_deps(to_search, res)
        return res
