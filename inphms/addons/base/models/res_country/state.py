from __future__ import annotations
import re

from inphms.orm import fields, models, api
from inphms.orm.fields import Domain


class ResCountryState(models.Model):
    _name = 'res.country.state'
    _description = "Country state"
    _order = 'code, id'
    _rec_names_search = ['name', 'code']

    country_id = fields.Many2one('res.country', string='Country', required=True, index=True)
    name = fields.Char(string='State Name', required=True,
               help='Administrative divisions of a country. E.g. Fed. State, Departement, Canton')
    code = fields.Char(string='State Code', help='The state code.', required=True)

    _name_code_uniq = models.Constraint(
        'unique(country_id, code)',
        "The code of the state must be unique by country!",
    )

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        result = []
        domain = Domain(domain or Domain.TRUE)
        # accepting 'in' as operator (see inphms/addons/base/tests/test_res_country.py)
        if operator == 'in':
            if limit is None:
                limit = 100  # force a limit
            for item in name:
                result.extend(self.name_search(item, domain, operator='=', limit=limit - len(result)))
                if len(result) == limit:
                    break
            return result
        # first search by code (with =ilike)
        if not operator in Domain.NEGATIVE_OPERATORS and name:
            states = self.search_fetch(domain & Domain('code', '=like', name), ['display_name'], limit=limit)
            result.extend((state.id, state.display_name) for state in states.sudo())
            domain &= Domain('id', 'not in', states.ids)
            if limit is not None:
                limit -= len(states)
                if limit <= 0:
                    return result
        # normal search
        result.extend(super().name_search(name, domain, operator, limit))
        return result

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if value and not operator in Domain.NEGATIVE_OPERATORS:
            if operator in ('ilike', '='):
                domain |= self._get_name_search_domain(value, operator)
            elif operator == 'in':
                domain |= Domain.OR(
                    self._get_name_search_domain(name, '=') for name in value
                )
        if country_id := self.env.context.get('country_id'):
            domain &= Domain('country_id', '=', country_id)
        return domain

    def _get_name_search_domain(self, name, operator):
        m = re.fullmatch(r"(?P<name>.+)\((?P<country>.+)\)", name)
        if m:
            return Domain([
                ('name', operator, m['name'].strip()),
                '|', ('country_id.name', 'ilike', m['country'].strip()),
                ('country_id.code', '=', m['country'].strip()),
            ])
        return Domain.FALSE

    @api.depends('country_id')
    @api.depends_context('formatted_display_name')
    def _compute_display_name(self):
        for record in self:
            if self.env.context.get('formatted_display_name'):
                record.display_name = f"{record.name} \t --{record.country_id.code}--"
            else:
                record.display_name = f"{record.name} ({record.country_id.code})"
