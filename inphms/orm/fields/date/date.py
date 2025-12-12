from __future__ import annotations
import typing as t
import pytz

from datetime import date, datetime

from .basedate import BaseDate
from .utils import DATE_LENGTH, DATE_FORMAT

if t.TYPE_CHECKING:
    from ...models import BaseModel

class Date(BaseDate[date]):
    """ Encapsulates a python :class:`date <datetime.date>` object. """
    type = 'date'
    _column_type = ('date', 'date')

    @staticmethod
    def today(*args) -> date:
        """ Return the current day in the format expected by the ORM.

            .. note:: This function may be used to compute default values.
        """
        return date.today()

    @staticmethod
    def context_today(record: BaseModel, timestamp: date | datetime | None = None) -> date:
        """ Return the current date as seen in the client's timezone in a format
            fit for date fields.

            .. note:: This method may be used to compute default values.

            :param record: recordset from which the timezone will be obtained.
            :param timestamp: optional datetime value to use instead of
                the current date and time (must be a datetime, regular dates
                can't be converted between timezones).
        """
        today = timestamp or datetime.now()
        tz = record.env.tz
        today_utc = pytz.utc.localize(today, is_dst=False) # type: ignore # UTC = no DST
        today = today_utc.astimezone(tz)
        return today.date()

    @staticmethod
    def to_date(value) -> date | None:
        """ Attempt to convert ``value`` to a :class:`date` object.

            .. warning::

                If a datetime object is given as value,
                it will be converted to a date object and all
                datetime-specific information will be lost (HMS, TZ, ...).

            :param value: value to convert.
            :type value: str or date or datetime
            :return: an object representing ``value``.
        """
        if not value:
            return None
        if isinstance(value, date):
            if isinstance(value, datetime):
                return value.date()
            return value
        value = value[:DATE_LENGTH]
        return datetime.strptime(value, DATE_FORMAT).date()

    # kept for backwards compatibility, but consider `from_string` as deprecated, will probably
    # be removed after V12
    from_string = to_date

    @staticmethod
    def to_string(value: date | t.Literal[False]) -> str | t.Literal[False]:
        """ Convert a :class:`date` or :class:`datetime` object to a string.

            :param value: value to convert.
            :return: a string representing ``value`` in the server's date format, if ``value`` is of
                type :class:`datetime`, the hours, minute, seconds, tzinfo will be truncated.
        """
        return value.strftime(DATE_FORMAT) if value else False

    def convert_to_cache(self, value, record, validate=True):
        if not value:
            return None
        if isinstance(value, datetime):
            # TODO: better fix data files (crm demo data)
            value = value.date()
            # raise TypeError("%s (field %s) must be string or date, not datetime." % (value, self))
        return self.to_date(value)

    def convert_to_export(self, value, record):
        return self.to_date(value) or ''

    def convert_to_display_name(self, value, record):
        return Date.to_string(value)
