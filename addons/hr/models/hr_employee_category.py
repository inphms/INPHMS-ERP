from __future__ import annotations

from random import randint

from inphms.orm import models, fields


class HrEmployeeCategory(models.Model):
    _name = 'hr.employee.category'

    _description = "Employee Category"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(string="Tag Name", required=True)
    color = fields.Integer(string='Color Index', default=_get_default_color)
    employee_ids = fields.Many2many('hr.employee', 'employee_category_rel', 'category_id', 'employee_id', string='Employees')

    _name_uniq = models.Constraint(
        'unique (name)',
        'Tag name already exists!',
    )
