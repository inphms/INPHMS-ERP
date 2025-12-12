from __future__ import annotations
import logging
import pytz
import typing as t

from inphms.databases import SQL, Query
from inphms.tools import dateutils as date_utils
from .utils import parse_field_expr, READ_GROUP_NUMBER_GRANULARITY
from ..field import Field

T = t.TypeVar("T")
if t.TYPE_CHECKING:
    from collections.abc import Callable
    from ...models import BaseModel


_logger = logging.getLogger("inphms.fields")


class BaseDate(Field[T | t.Literal[False]], t.Generic[T]):
    """ Common field properties for Date and Datetime. """

    start_of = staticmethod(date_utils.start_of)
    end_of = staticmethod(date_utils.end_of)
    add = staticmethod(date_utils.add)
    subtract = staticmethod(date_utils.subtract)

    def expression_getter(self, field_expr):
        _fname, property_name = parse_field_expr(field_expr)
        if not property_name:
            return super().expression_getter(field_expr)

        get_value = self.__get__
        get_property = self._expression_property_getter(property_name)
        return lambda record: (value := get_value(record)) and get_property(value)

    def _expression_property_getter(self, property_name: str) -> Callable[[T], t.Any]:
        """ Return a function that maps a field value (date or datetime) to the
        given ``property_name``.
        """
        match property_name:
            case 'tz':
                return lambda value: value
            case 'year_number':
                return lambda value: value.year
            case 'quarter_number':
                return lambda value: value.month // 4 + 1
            case 'month_number':
                return lambda value: value.month
            case 'iso_week_number':
                return lambda value: value.isocalendar().week
            case 'day_of_year':
                return lambda value: value.timetuple().tm_yday
            case 'day_of_month':
                return lambda value: value.day
            case 'day_of_week':
                return lambda value: value.timetuple().tm_wday
            case 'hour_number' if self.type == 'datetime':
                return lambda value: value.hour
            case 'minute_number' if self.type == 'datetime':
                return lambda value: value.minute
            case 'second_number' if self.type == 'datetime':
                return lambda value: value.second
            case 'hour_number' | 'minute_number' | 'second_number':
                # for dates, it is always 0
                return lambda value: 0
        assert property_name not in READ_GROUP_NUMBER_GRANULARITY, f"Property not implemented {property_name}"
        raise ValueError(
            f"Error when processing the granularity {property_name} is not supported. "
            f"Only {', '.join(READ_GROUP_NUMBER_GRANULARITY.keys())} are supported"
        )

    def property_to_sql(self, field_sql: SQL, property_name: str, model: BaseModel, alias: str, query: Query) -> SQL:
        sql_expr = field_sql
        if self.type == 'datetime' and (timezone := model.env.context.get('tz')):
            # only use the timezone from the context
            if timezone in pytz.all_timezones_set:
                sql_expr = SQL("timezone(%s, timezone('UTC', %s))", timezone, sql_expr)
            else:
                _logger.warning("Grouping in unknown / legacy timezone %r", timezone)
        if property_name == 'tz':
            # set only the timezone
            return sql_expr
        if property_name not in READ_GROUP_NUMBER_GRANULARITY:
            raise ValueError(f'Error when processing the granularity {property_name} is not supported. Only {", ".join(READ_GROUP_NUMBER_GRANULARITY.keys())} are supported')
        granularity = READ_GROUP_NUMBER_GRANULARITY[property_name]
        sql_expr = SQL('date_part(%s, %s)', granularity, sql_expr)
        return sql_expr

    def convert_to_column(self, value, record, values=None, validate=True):
        # we can write date/datetime directly using psycopg
        # except for company_dependent fields where we expect a string value
        value = self.convert_to_cache(value, record, validate=validate)
        if value and self.company_dependent:
            value = self.to_string(value)
        return value
