from __future__ import annotations

from collections.abc import Iterable

from inphms.orm.models.utils import check_company_domain_parent_of
from inphms.tools import parse_date
from inphms.exceptions import ValidationError, UserError
from inphms.orm import fields, models, api


class ResCurrencyRate(models.Model):
    _name = 'res.currency.rate'
    _description = "Currency Rate"
    _rec_names_search = ['name', 'rate']
    _order = "name desc, id"
    _check_company_domain = check_company_domain_parent_of

    name = fields.Date(string='Date', required=True, index=True,
                           default=fields.Date.context_today)
    rate = fields.Float(
        digits=0,
        aggregator="avg",
        help='The rate of the currency to the currency of rate 1',
        string='Technical Rate'
    )
    company_rate = fields.Float(
        digits=0,
        compute="_compute_company_rate",
        inverse="_inverse_company_rate",
        aggregator="avg",
        help="The currency of rate 1 to the rate of the currency.",
    )
    inverse_company_rate = fields.Float(
        digits=0,
        compute="_compute_inverse_company_rate",
        inverse="_inverse_inverse_company_rate",
        aggregator="avg",
        help="The rate of the currency to the currency of rate 1 ",
    )
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True, required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company.root_id)

    _unique_name_per_day = models.Constraint(
        'unique (name,currency_id,company_id)',
        "Only one currency rate per day allowed!",
    )
    _currency_rate_check = models.Constraint(
        'CHECK (rate>0)',
        "The currency rate must be strictly positive.",
    )

    def _sanitize_vals(self, vals):
        if 'inverse_company_rate' in vals and ('company_rate' in vals or 'rate' in vals):
            del vals['inverse_company_rate']
        if 'company_rate' in vals and 'rate' in vals:
            del vals['company_rate']
        return vals

    def write(self, vals):
        self.env['res.currency'].invalidate_model(['inverse_rate'])
        return super().write(self._sanitize_vals(vals))

    @api.model_create_multi
    def create(self, vals_list):
        self.env['res.currency'].invalidate_model(['inverse_rate'])
        return super().create([self._sanitize_vals(vals) for vals in vals_list])

    def _get_latest_rate(self):
        # Make sure 'name' is defined when creating a new rate.
        if not self.name:
            raise UserError(self.env._("The name for the current rate is empty.\nPlease set it."))
        return self.currency_id.rate_ids.sudo().filtered(lambda x: (
            x.rate
            and x.company_id == (self.company_id or self.env.company.root_id)
            and x.name < (self.name or fields.Date.today())
        )).sorted('name')[-1:]

    def _get_last_rates_for_companies(self, companies):
        return {
            company: company.sudo().currency_id.rate_ids.filtered(lambda x: (
                x.rate
                and x.company_id == company or not x.company_id
            )).sorted('name')[-1:].rate or 1
            for company in companies
        }

    @api.depends('currency_id', 'company_id', 'name')
    def _compute_rate(self):
        for currency_rate in self:
            currency_rate.rate = currency_rate.rate or currency_rate._get_latest_rate().rate or 1.0

    @api.depends('rate', 'name', 'currency_id', 'company_id', 'currency_id.rate_ids.rate')
    @api.depends_context('company')
    def _compute_company_rate(self):
        last_rate = self.env['res.currency.rate']._get_last_rates_for_companies(self.company_id | self.env.company.root_id)
        for currency_rate in self:
            company = currency_rate.company_id or self.env.company.root_id
            currency_rate.company_rate = (currency_rate.rate or currency_rate._get_latest_rate().rate or 1.0) / last_rate[company]

    @api.onchange('company_rate')
    def _inverse_company_rate(self):
        last_rate = self.env['res.currency.rate']._get_last_rates_for_companies(self.company_id | self.env.company.root_id)
        for currency_rate in self:
            company = currency_rate.company_id or self.env.company.root_id
            currency_rate.rate = currency_rate.company_rate * last_rate[company]

    @api.depends('company_rate')
    def _compute_inverse_company_rate(self):
        for currency_rate in self:
            if not currency_rate.company_rate:
                currency_rate.company_rate = 1.0
            currency_rate.inverse_company_rate = 1.0 / currency_rate.company_rate

    @api.onchange('inverse_company_rate')
    def _inverse_inverse_company_rate(self):
        for currency_rate in self:
            if not currency_rate.inverse_company_rate:
                currency_rate.inverse_company_rate = 1.0
            currency_rate.company_rate = 1.0 / currency_rate.inverse_company_rate

    @api.onchange('company_rate')
    def _onchange_rate_warning(self):
        latest_rate = self._get_latest_rate()
        if latest_rate:
            diff = (latest_rate.rate - self.rate) / latest_rate.rate
            if abs(diff) > 0.2:
                return {
                    'warning': {
                        'title': self.env._("Warning for %s", self.currency_id.name),
                        'message': self.env._(
                            "The new rate is quite far from the previous rate.\n"
                            "Incorrect currency rates may cause critical problems, make sure the rate is correct!"
                        )
                    }
                }

    @api.constrains('company_id')
    def _check_company_id(self):
        for rate in self:
            if rate.company_id.sudo().parent_id:
                raise ValidationError(self.env._("Currency rates should only be created for main companies"))

    @api.model
    def _search_display_name(self, operator, value):
        if isinstance(value, Iterable) and not isinstance(value, str):
            value = [parse_date(self.env, v) for v in value]
        else:
            value = parse_date(self.env, value)
        return super()._search_display_name(operator, value)

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        """The override of _get_view changing the rate field labels according to the company currency
        makes the view cache dependent on the company currency"""
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + ((self.env['res.company'].browse(self.env.context.get('company_id')) or self.env.company).currency_id.name,)

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'list':
            names = {
                'company_currency_name': (self.env['res.company'].browse(self.env.context.get('company_id')) or self.env.company).currency_id.name,
                'rate_currency_name': self.env['res.currency'].browse(self.env.context.get('active_id')).name or 'Unit',
            }
            for name, label in [['company_rate', self.env._('%(rate_currency_name)s per %(company_currency_name)s', **names)],
                                ['inverse_company_rate', self.env._('%(company_currency_name)s per %(rate_currency_name)s', **names)]]:

                if (node := arch.find(f"./field[@name='{name}']")) is not None:
                    node.set('string', label)
        return arch, view
