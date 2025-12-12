from __future__ import annotations

from collections import defaultdict

from .utils import _, ValidationError
from inphms.orm import models, fields, api


class IrModuleCategory(models.Model):
    _name = 'ir.module.category'
    _description = "Application"
    _order = 'sequence, name, id'
    _allow_sudo_commands = False

    name = fields.Char(string='Name', required=True, translate=True)
    parent_id = fields.Many2one('ir.module.category', string='Parent Application', index=True)
    child_ids = fields.One2many('ir.module.category', 'parent_id', string='Child Applications')
    module_ids = fields.One2many('ir.module.module', 'category_id', string='Modules')
    privilege_ids = fields.One2many('res.groups.privilege', 'category_id', string='Privileges')
    description = fields.Text(string='Description', translate=True)
    sequence = fields.Integer(string='Sequence')
    visible = fields.Boolean(string='Visible', default=True)
    exclusive = fields.Boolean(string='Exclusive')
    xml_id = fields.Char(string='External ID', compute='_compute_xml_id')

    submenu_icon = fields.Char(string="Submenu Icon") # font awesome icon

    def _compute_xml_id(self):
        xml_ids = defaultdict(list)
        domain = [('model', '=', self._name), ('res_id', 'in', self.ids)]
        for data in self.env['ir.model.data'].sudo().search_read(domain, ['module', 'name', 'res_id']):
            xml_ids[data['res_id']].append("%s.%s" % (data['module'], data['name']))
        for cat in self:
            cat.xml_id = xml_ids.get(cat.id, [''])[0]

    @api.constrains('parent_id')
    def _check_parent_not_circular(self):
        if self._has_cycle():
            raise ValidationError(_("Error ! You cannot create recursive categories."))

