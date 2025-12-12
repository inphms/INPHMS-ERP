from __future__ import annotations

from .utils import DEP_STATES
from inphms.orm import api, models, fields


class IrModuleModuleExclusion(models.Model):
    _name = 'ir.module.module.exclusion'
    _description = "Module exclusion"
    _allow_sudo_commands = False

    # the exclusion name
    name = fields.Char(index=True)

    # the module that excludes it
    module_id = fields.Many2one('ir.module.module', 'Module', ondelete='cascade')

    # the module corresponding to the exclusion, and its status
    exclusion_id = fields.Many2one('ir.module.module', 'Exclusion Module',
                                   compute='_compute_exclusion', search='_search_exclusion')
    state = fields.Selection(DEP_STATES, string='Status', compute='_compute_state')

    @api.depends('name')
    def _compute_exclusion(self):
        # retrieve all modules corresponding to the exclusion names
        names = {excl.name for excl in self}
        mods = self.env['ir.module.module'].search([('name', 'in', names)])

        # index modules by name, and assign dependencies
        name_mod = {mod.name: mod for mod in mods}
        for excl in self:
            excl.exclusion_id = name_mod.get(excl.name)

    def _search_exclusion(self, operator, value):
        if operator not in ('in', 'any'):
            return NotImplemented
        modules = self.env['ir.module.module'].browse(value)
        return [('name', 'in', modules.mapped('name'))]

    @api.depends('exclusion_id.state')
    def _compute_state(self):
        for exclusion in self:
            exclusion.state = exclusion.exclusion_id.state or 'unknown'
