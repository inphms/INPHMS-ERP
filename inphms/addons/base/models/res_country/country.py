from __future__ import annotations
import re

from inphms.orm.fields import Domain
from inphms import tools
from inphms.tools import _
from inphms.exceptions import UserError
from .utils import FLAG_MAPPING, NO_FLAG_COUNTRIES
from inphms.orm import models, api, fields


class ResCountry(models.Model):
    _name = 'res.country'
    _description = 'Country'
    _order = 'name, id'
    _rec_names_search = ['name', 'code']

    name = fields.Char(
        string='Country Name', required=True, translate=True)
    code = fields.Char(
        string='Country Code', size=2,
        required=True,
        help='The ISO country code in two chars. \nYou can use this field for quick search.')
    address_format = fields.Text(string="Layout in Reports",
        help="Display format to use for addresses belonging to this country.\n\n"
             "You can use python-style string pattern with all the fields of the address "
             "(for example, use '%(street)s' to display the field 'street') plus"
             "\n%(state_name)s: the name of the state"
             "\n%(state_code)s: the code of the state"
             "\n%(country_name)s: the name of the country"
             "\n%(country_code)s: the code of the country",
        default='%(street)s\n%(street2)s\n%(city)s %(state_code)s %(zip)s\n%(country_name)s')
    address_view_id = fields.Many2one(
        comodel_name='ir.ui.view', string="Input View",
        domain=[('model', '=', 'res.partner'), ('type', '=', 'form')],
        help="Use this field if you want to replace the usual way to encode a complete address. "
             "Note that the address_format field is used to modify the way to display addresses "
             "(in reports for example), while this field is used to modify the input form for "
             "addresses.")
    currency_id = fields.Many2one('res.currency', string='Currency')
    image_url = fields.Char(
        compute="_compute_image_url", string="Flag",
        help="Url of static flag image",
    )
    phone_code = fields.Integer(string='Country Calling Code')
    country_group_ids = fields.Many2many('res.country.group', 'res_country_res_country_group_rel',
                         'res_country_id', 'res_country_group_id', string='Country Groups')
    country_group_codes = fields.Json(compute="_compute_country_group_codes")
    state_ids = fields.One2many('res.country.state', 'country_id', string='States')
    name_position = fields.Selection([
            ('before', 'Before Address'),
            ('after', 'After Address'),
        ], string="Customer Name Position", default="before",
        help="Determines where the customer/company name should be placed, i.e. after or before the address.")
    vat_label = fields.Char(string='Vat Label', translate=True, prefetch=True, help="Use this field if you want to change vat label.")

    state_required = fields.Boolean(default=False)
    zip_required = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        "The name of the country must be unique!",
    )
    _code_uniq = models.Constraint(
        'unique (code)',
        "The code of the country must be unique!",
    )

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        result = []
        domain = Domain(domain or Domain.TRUE)
        # first search by code
        if not operator in Domain.NEGATIVE_OPERATORS and name and len(name) == 2:
            countries = self.search_fetch(domain & Domain('code', operator, name), ['display_name'], limit=limit)
            result.extend((country.id, country.display_name) for country in countries.sudo())
            domain &= Domain('id', 'not in', countries.ids)
            if limit is not None:
                limit -= len(countries)
                if limit <= 0:
                    return result
        # normal search
        result.extend(super().name_search(name, domain, operator, limit))
        return result

    @api.model
    @tools.ormcache('code', cache='stable')
    def _phone_code_for(self, code):
        return self.search([('code', '=', code)]).phone_code

    @api.model_create_multi
    def create(self, vals_list):
        self.env.registry.clear_cache('stable')
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].upper()
        res = super().write(vals)
        if ('code' in vals or 'phone_code' in vals):
            # Intentionally simplified by not clearing the cache in create and unlink.
            self.env.registry.clear_cache('stable')
        if 'address_view_id' in vals or 'vat_label' in vals:
            # Changing the address view of the company must invalidate the view cached for res.partner
            # because of _view_get_address
            # Same goes for vat_label
            # because of _get_view override from FormatVATLabelMixin
            self.env.registry.clear_cache('templates')
        return res

    def unlink(self):
        self.env.registry.clear_cache('stable')
        return super().unlink()

    def get_address_fields(self):
        self.ensure_one()
        return re.findall(r'\((.+?)\)', self.address_format)

    @api.depends('code')
    def _compute_image_url(self):
        for country in self:
            if not country.code or country.code in NO_FLAG_COUNTRIES:
                country.image_url = False
            else:
                code = FLAG_MAPPING.get(country.code, country.code.lower())
                country.image_url = "/base/static/img/country_flags/%s.png" % code

    @api.constrains('address_format')
    def _check_address_format(self):
        for record in self:
            if record.address_format:
                address_fields = self.env['res.partner']._formatting_address_fields() + ['state_code', 'state_name', 'country_code', 'country_name', 'company_name']
                try:
                    record.address_format % {i: 1 for i in address_fields}
                except (ValueError, KeyError):
                    raise UserError(_('The layout contains an invalid format key'))

    @api.depends('country_group_ids')
    def _compute_country_group_codes(self):
        '''If a country has no associated country groups, assign [''] to country_group_codes.
        This prevents storing [] as False, which helps avoid iteration over a False value and
        maintains a valid structure.
        '''
        for country in self:
            country.country_group_codes = [g.code for g in country.country_group_ids if g.code] or ['']
