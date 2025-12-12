from __future__ import annotations

from inphms.orm import fields, models, api


class ResCountryGroup(models.Model):
    _name = 'res.country.group'
    _description = "Country Group"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(string="Code")
    country_ids = fields.Many2many('res.country', 'res_country_res_country_group_rel',
                                   'res_country_group_id', 'res_country_id', string='Countries')

    _check_code_uniq = models.Constraint(
        'unique(code)',
        'The country group code must be unique!',
    )

    def _sanitize_vals(self, vals):
        if code := vals.get('code'):
            vals['code'] = code.upper()
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._sanitize_vals(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._sanitize_vals(vals))
