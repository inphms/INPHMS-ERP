from __future__ import annotations
import pytz
import typing as t

from datetime import date, datetime, time

from . import BaseDate
from .utils import DATETIME_FORMAT, parse_field_expr

if t.TYPE_CHECKING:
    from collections.abc import Callable
    from ...models import BaseModel

class Datetime(BaseDate[datetime]):
    """ Encapsulates a python :class:`datetime <datetime.datetime>` object. """
    type = 'datetime'
    _column_type = ('timestamp', 'timestamp')

    @staticmethod
    def now(*args) -> datetime:
        """ Return the current day and time in the format expected by the ORM.

            .. note:: This function may be used to compute default values.
        """
        # microseconds must be annihilated as they don't comply with the server datetime format
        return datetime.now().replace(microsecond=0)

    @staticmethod
    def today(*args) -> datetime:
        """ Return the current day, at midnight (00:00:00)."""
        return Datetime.now().replace(hour=0, minute=0, second=0)

    @staticmethod
    def context_timestamp(record: BaseModel, timestamp: datetime) -> datetime:
        """ Return the given timestamp converted to the client's timezone.

            .. note:: This method is *not* meant for use as a default initializer,
                because datetime fields are automatically converted upon
                display on client side. For default values, :meth:`now`
                should be used instead.

            :param record: recordset from which the timezone will be obtained.
            :param datetime timestamp: naive datetime value (expressed in UTC)
                to be converted to the client timezone.
            :return: timestamp converted to timezone-aware datetime in context timezone.
            :rtype: datetime
        """
        assert isinstance(timestamp, datetime), 'Datetime instance expected'
        tz = record.env.tz
        utc_timestamp = pytz.utc.localize(timestamp, is_dst=False)  # UTC = no DST
        timestamp = utc_timestamp.astimezone(tz)
        return timestamp

    @staticmethod
    def to_datetime(value) -> datetime | None:
        """ Convert an ORM ``value`` into a :class:`datetime` value.

            :param value: value to convert.
            :type value: str or date or datetime
            :return: an object representing ``value``.
        """
        if not value:
            return None
        if isinstance(value, date):
            if isinstance(value, datetime):
                if value.tzinfo:
                    raise ValueError("Datetime field expects a naive datetime: %s" % value)
                return value
            return datetime.combine(value, time.min)

        # TODO: fix data files
        return datetime.strptime(value, DATETIME_FORMAT[:len(value)-2])

    # kept for backwards compatibility, but consider `from_string` as deprecated, will probably
    # be removed after V12
    from_string = to_datetime

    @staticmethod
    def to_string(value: datetime | t.Literal[False]) -> str | t.Literal[False]:
        """Convert a :class:`datetime` or :class:`date` object to a string.

        :param value: value to convert.
        :type value: datetime or date
        :return: a string representing ``value`` in the server's datetime format,
            if ``value`` is of type :class:`date`,
            the time portion will be midnight (00:00:00).
        """
        return value.strftime(DATETIME_FORMAT) if value else False

    def expression_getter(self, field_expr: str) -> Callable[[BaseModel], t.Any]:
        if field_expr == self.name:
            return self.__get__
        _fname, property_name = parse_field_expr(field_expr)
        get_property = self._expression_property_getter(property_name)

        def getter(record):
            dt = self.__get__(record)
            if not dt:
                return False
            if (tz := record.env.context.get('tz')) and tz in pytz.all_timezones_set:
                # only use the timezone from the context
                dt = dt.astimezone(pytz.timezone(tz))
            return get_property(dt)

        return getter

    def convert_to_cache(self, value, record, validate=True):
        return self.to_datetime(value)

    def convert_to_export(self, value, record):
        value = self.convert_to_display_name(value, record)
        return self.to_datetime(value) or ''

    def convert_to_display_name(self, value, record):
        if not value:
            return False
        return Datetime.to_string(Datetime.context_timestamp(record, value))
