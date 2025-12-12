from __future__ import annotations
import typing as t

from ..field import Field
from inphms.tools import Sentinel, SENTINEL, float_repr
from inphms.exceptions import AccessError

if t.TYPE_CHECKING:
    from inphms.modules import Environment
    from inphms.orm.models import BaseModel

class Monetary(Field[float]):
    """ Encapsulates a :class:`float` expressed in a given
        :class:`res_currency<inphms.addons.base.models.res_currency.Currency>`.

        The decimal precision and currency symbol are taken from the ``currency_field`` attribute.

        :param str currency_field: name of the :class:`Many2one` field
            holding the :class:`res_currency <inphms.addons.base.models.res_currency.Currency>`
            this monetary field is expressed in (default: `\'currency_id\'`)
    """
    type = 'monetary'
    write_sequence = 10
    _column_type = ('numeric', 'numeric')
    falsy_value = 0.0

    currency_field: Field | None = None
    aggregator = 'sum'

    def __init__(self, string: str | Sentinel = SENTINEL, currency_field: str | Sentinel = SENTINEL, **kwargs):
        super().__init__(string=string, currency_field=currency_field, **kwargs)

    def _description_currency_field(self, env: Environment) -> str | None:
        return self.get_currency_field(env[self.model_name])

    def _description_aggregator(self, env: Environment):
        model = env[self.model_name]
        query = model._as_query(ordered=False)
        currency_field_name = self.get_currency_field(model)
        currency_field = model._fields[currency_field_name]
        # The currency field needs to be aggregable too
        if not currency_field.column_type or not currency_field.store:
            try:
                model._read_group_select(f"{currency_field_name}:array_agg_distinct", query)
            except (ValueError, AccessError):
                return None

        return super()._description_aggregator(env)

    def get_currency_field(self, model: BaseModel) -> str | None:
        """ Return the name of the currency field. """
        return self.currency_field or (
            'currency_id' if 'currency_id' in model._fields else
            'x_currency_id' if 'x_currency_id' in model._fields else
            None
        )

    def setup_nonrelated(self, model):
        super().setup_nonrelated(model)
        assert self.get_currency_field(model) in model._fields, \
            "Field %s with unknown currency_field %r" % (self, self.get_currency_field(model))

    def setup_related(self, model):
        super().setup_related(model)
        if self.inherited:
            self.currency_field = self.related_field.get_currency_field(model.env[self.related_field.model_name])
        assert self.get_currency_field(model) in model._fields, \
            "Field %s with unknown currency_field %r" % (self, self.get_currency_field(model))

    def convert_to_column_insert(self, value, record, values=None, validate=True):
        # retrieve currency from values or record
        currency_field_name = self.get_currency_field(record)
        currency_field = record._fields[currency_field_name]
        if values and currency_field_name in values:
            dummy = record.new({currency_field_name: values[currency_field_name]})
            currency = dummy[currency_field_name]
        elif values and currency_field.related and currency_field.related.split('.')[0] in values:
            related_field_name = currency_field.related.split('.')[0]
            dummy = record.new({related_field_name: values[related_field_name]})
            currency = dummy[currency_field_name]
        else:
            # Note: this is wrong if 'record' is several records with different
            # currencies, which is functional nonsense and should not happen
            # BEWARE: do not prefetch other fields, because 'value' may be in
            # cache, and would be overridden by the value read from database!
            currency = record[:1].sudo().with_context(prefetch_fields=False)[currency_field_name]
            currency = currency.with_env(record.env)

        value = float(value or 0.0)
        if currency:
            return float_repr(currency.round(value), currency.decimal_places)
        return value

    def convert_to_cache(self, value, record, validate=True):
        # cache format: float
        value = float(value or 0.0)
        if value and validate:
            # FIXME @rco-inphms: currency may not be already initialized if it is
            # a function or related field!
            # BEWARE: do not prefetch other fields, because 'value' may be in
            # cache, and would be overridden by the value read from database!
            currency_field = self.get_currency_field(record)
            currency = record.sudo().with_context(prefetch_fields=False)[currency_field]
            if len(currency) > 1:
                raise ValueError("Got multiple currencies while assigning values of monetary field %s" % str(self))
            elif currency:
                value = currency.with_env(record.env).round(value)
        return value

    def convert_to_record(self, value, record):
        return value or 0.0

    def convert_to_read(self, value, record, use_display_name=True):
        return value

    def convert_to_write(self, value, record):
        return value

    def convert_to_export(self, value, record):
        if value or value == 0.0:
            return value
        return ''

    def _filter_not_equal(self, records: BaseModel, cache_value: t.Any) -> BaseModel:
        records = super()._filter_not_equal(records, cache_value)
        if not records:
            return records
        # check that the values were rounded properly when put in cache
        # see fix inphms/inphms#177200 (commit 7164d5295904b08ec3a0dc1fb54b217671ff531c)
        env = records.env
        field_cache = self._get_cache(env)
        currency_field = records._fields[self.get_currency_field(records)]
        return records.browse(
            record_id
            for record_id, record_sudo in zip(
                records._ids, records.sudo().with_context(prefetch_fields=False)
            )
            if not (
                (value := field_cache.get(record_id))
                and (currency := currency_field.__get__(record_sudo))
                and currency.with_env(env).round(value) == cache_value
            )
        )
