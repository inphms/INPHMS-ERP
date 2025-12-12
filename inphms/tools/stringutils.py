from __future__ import annotations
import warnings
import re
import typing as t
import babel
import babel.dates
import datetime
import pytz

from difflib import HtmlDiff

from .i18n import get_lang, babel_locale_parse
from .floatutils import float_round

if t.TYPE_CHECKING:
    from inphms.modules import Environment


__all__ = ['str2bool', 'unquote', 'human_size', "get_iso_codes", 'street_split', 'ADDRESS_REGEX',
           "format_amount", 'format_duration', "format_date", "get_diff", "format_time",
           "format_datetime", "formatLang"]

NON_BREAKING_SPACE = u'\N{NO-BREAK SPACE}'


def str2bool(s: str, default: bool | None = None) -> bool:
    # allow this (for now?) because it's used for get_param
    if type(s) is bool:
        return s  # type: ignore

    if not isinstance(s, str):
        warnings.warn(
            f"Passed a non-str to `str2bool`: {s}",
            DeprecationWarning,
            stacklevel=2,
        )

        if default is None:
            raise ValueError('Use 0/1/yes/no/true/false/on/off')
        return bool(default)

    s = s.lower()
    if s in ('y', 'yes', '1', 'true', 't', 'on'):
        return True
    if s in ('n', 'no', '0', 'false', 'f', 'off'):
        return False
    if default is None:
        raise ValueError('Use 0/1/yes/no/true/false/on/off')
    return bool(default)


class unquote(str):
    """A subclass of str that implements repr() without enclosing quotation marks
       or escaping, keeping the original string untouched. The name come from Lisp's unquote.
       One of the uses for this is to preserve or insert bare variable names within dicts during eval()
       of a dict's repr(). Use with care.

       Some examples (notice that there are never quotes surrounding
       the ``active_id`` name:

       >>> unquote('active_id')
       active_id
       >>> d = {'test': unquote('active_id')}
       >>> d
       {'test': active_id}
       >>> print d
       {'test': active_id}
    """
    __slots__ = ()

    def __repr__(self):
        return self


def human_size(sz: float | str) -> str | t.Literal[False]:
    """
    Return the size in a human readable format
    """
    if not sz:
        return False
    units = ('bytes', 'Kb', 'Mb', 'Gb', 'Tb')
    if isinstance(sz, str):
        sz=len(sz)
    s, i = float(sz), 0
    while s >= 1024 and i < len(units)-1:
        s /= 1024
        i += 1
    return "%0.2f %s" % (s, units[i])


def get_iso_codes(lang: str) -> str:
    if lang.find('_') != -1:
        lang_items = lang.split('_')
        if lang_items[0] == lang_items[1].lower():
            lang = lang_items[0]
    return lang


def get_diff(data_from, data_to, custom_style=False, dark_color_scheme=False):
    """
    Return, in an HTML table, the diff between two texts.

    :param tuple data_from: tuple(text, name), name will be used as table header
    :param tuple data_to: tuple(text, name), name will be used as table header
    :param tuple custom_style: string, style css including <style> tag.
    :param bool dark_color_scheme: true if dark color scheme is used
    :return: a string containing the diff in an HTML table format.
    """
    def handle_style(html_diff, custom_style, dark_color_scheme):
        """ The HtmlDiff lib will add some useful classes on the DOM to
        identify elements. Simply append to those classes some BS4 ones.
        For the table to fit the modal width, some custom style is needed.
        """
        to_append = {
            'diff_header': 'bg-600 text-light text-center align-top px-2',
            'diff_next': 'd-none',
        }
        for old, new in to_append.items():
            html_diff = html_diff.replace(old, "%s %s" % (old, new))
        html_diff = html_diff.replace('nowrap', '')
        colors = ('#7f2d2f', '#406a2d', '#51232f', '#3f483b') if dark_color_scheme else (
            '#ffc1c0', '#abf2bc', '#ffebe9', '#e6ffec')
        html_diff += custom_style or '''
            <style>
                .modal-dialog.modal-lg:has(table.diff) {
                    max-width: 1600px;
                    padding-left: 1.75rem;
                    padding-right: 1.75rem;
                }
                table.diff { width: 100%%; }
                table.diff th.diff_header { width: 50%%; }
                table.diff td.diff_header { white-space: nowrap; }
                table.diff td.diff_header + td { width: 50%%; }
                table.diff td { word-break: break-all; vertical-align: top; }
                table.diff .diff_chg, table.diff .diff_sub, table.diff .diff_add {
                    display: inline-block;
                    color: inherit;
                }
                table.diff .diff_sub, table.diff td:nth-child(3) > .diff_chg { background-color: %s }
                table.diff .diff_add, table.diff td:nth-child(6) > .diff_chg { background-color: %s }
                table.diff td:nth-child(3):has(>.diff_chg, .diff_sub) { background-color: %s }
                table.diff td:nth-child(6):has(>.diff_chg, .diff_add) { background-color: %s }
            </style>
        ''' % colors
        return html_diff

    diff = HtmlDiff(tabsize=2).make_table(
        data_from[0].splitlines(),
        data_to[0].splitlines(),
        data_from[1],
        data_to[1],
        context=True,  # Show only diff lines, not all the code
        numlines=3,
    )
    return handle_style(diff, custom_style, dark_color_scheme)


ADDRESS_REGEX = re.compile(r'^(.*?)(\s[0-9][0-9\S]*)?(?: - (.+))?$', flags=re.DOTALL)
def street_split(street):
    match = ADDRESS_REGEX.match(street or '')
    results = match.groups('') if match else ('', '', '')
    return {
        'street_name': results[0].strip(),
        'street_number': results[1].strip(),
        'street_number2': results[2],
    }


def format_amount(env: Environment, amount: float, currency, lang_code: str | None = None, trailing_zeroes: bool = True) -> str:
    fmt = "%.{0}f".format(currency.decimal_places)
    lang = env['res.lang'].browse(get_lang(env, lang_code).id)

    formatted_amount = lang.format(fmt, currency.round(amount), grouping=True)\
        .replace(r' ', u'\N{NO-BREAK SPACE}').replace(r'-', u'-\N{ZERO WIDTH NO-BREAK SPACE}')

    if not trailing_zeroes:
        formatted_amount = re.sub(fr'{re.escape(lang.decimal_point)}?0+$', '', formatted_amount)

    pre = post = u''
    if currency.position == 'before':
        pre = u'{symbol}\N{NO-BREAK SPACE}'.format(symbol=currency.symbol or '')
    else:
        post = u'\N{NO-BREAK SPACE}{symbol}'.format(symbol=currency.symbol or '')

    return u'{pre}{0}{post}'.format(formatted_amount, pre=pre, post=post)


def format_decimalized_number(number: float, decimal: int = 1) -> str:
    """Format a number to display to nearest metrics unit next to it.

    Do not display digits if all visible digits are null.
    Do not display units higher then "Tera" because most people don't know what
    a "Yotta" is.

    ::

        >>> format_decimalized_number(123_456.789)
        123.5k
        >>> format_decimalized_number(123_000.789)
        123k
        >>> format_decimalized_number(-123_456.789)
        -123.5k
        >>> format_decimalized_number(0.789)
        0.8
    """
    for unit in ['', 'k', 'M', 'G']:
        if abs(number) < 1000.0:
            return "%g%s" % (round(number, decimal), unit)
        number /= 1000.0
    return "%g%s" % (round(number, decimal), 'T')


def format_decimalized_amount(amount: float, currency=None) -> str:
    """Format an amount to display the currency and also display the metric unit
    of the amount.

    ::

        >>> format_decimalized_amount(123_456.789, env.ref("base.USD"))
        $123.5k
    """
    formated_amount = format_decimalized_number(amount)

    if not currency:
        return formated_amount

    if currency.position == 'before':
        return "%s%s" % (currency.symbol or '', formated_amount)

    return "%s %s" % (formated_amount, currency.symbol or '')


def format_duration(value: float) -> str:
    """ Format a float: used to display integral or fractional values as
        human-readable time spans (e.g. 1.5 as "01:30").
    """
    hours, minutes = divmod(abs(value) * 60, 60)
    minutes = round(minutes)
    if minutes == 60:
        minutes = 0
        hours += 1
    if value < 0:
        return '-%02d:%02d' % (hours, minutes)
    return '%02d:%02d' % (hours, minutes)


def format_date(
    env: Environment,
    value: datetime.datetime | datetime.date | str,
    lang_code: str | None = None,
    date_format: str | t.Literal[False] = False,
) -> str:
    """
        Formats the date in a given format.

        :param env: an environment.
        :param date, datetime or string value: the date to format.
        :param string lang_code: the lang code, if not specified it is extracted from the
            environment context.
        :param string date_format: the format or the date (LDML format), if not specified the
            default format of the lang.
        :return: date formatted in the specified format.
        :rtype: string
    """
    if not value:
        return ''
    from inphms.orm.fields import Datetime  # noqa: PLC0415
    from inphms import DATE_LENGTH, posix_to_ldml
    if isinstance(value, str):
        if len(value) < DATE_LENGTH:
            return ''
        if len(value) > DATE_LENGTH:
            # a datetime, convert to correct timezone
            value = Datetime.from_string(value)
            value = Datetime.context_timestamp(env['res.lang'], value)
        else:
            value = Datetime.from_string(value)
    elif isinstance(value, datetime.datetime) and not value.tzinfo:
        # a datetime, convert to correct timezone
        value = Datetime.context_timestamp(env['res.lang'], value)

    lang = get_lang(env, lang_code)
    locale = babel_locale_parse(lang.code)
    if not date_format:
        date_format = posix_to_ldml(lang.date_format, locale=locale)

    assert isinstance(value, datetime.date)  # datetime is a subclass of date
    return babel.dates.format_date(value, format=date_format, locale=locale)


def format_datetime(
    env: Environment,
    value: datetime.datetime | str,
    tz: str | t.Literal[False] = False,
    dt_format: str = 'medium',
    lang_code: str | None = None,
) -> str:
    """ Formats the datetime in a given format.

    :param env:
    :param str|datetime value: naive datetime to format either in string or in datetime
    :param str tz: name of the timezone  in which the given datetime should be localized
    :param str dt_format: one of “full”, “long”, “medium”, or “short”, or a custom date/time pattern compatible with `babel` lib
    :param str lang_code: ISO code of the language to use to render the given datetime
    :rtype: str
    """
    if not value:
        return ''
    if isinstance(value, str):
        from inphms.orm.fields import Datetime  # noqa: PLC0415
        timestamp = Datetime.from_string(value)
    else:
        timestamp = value

    tz_name = tz or env.user.tz or 'UTC'
    utc_datetime = pytz.utc.localize(timestamp, is_dst=False)
    try:
        context_tz = pytz.timezone(tz_name)
        localized_datetime = utc_datetime.astimezone(context_tz)
    except Exception:
        localized_datetime = utc_datetime

    lang = get_lang(env, lang_code)

    locale = babel_locale_parse(lang.code or lang_code)  # lang can be inactive, so `lang`is empty
    if not dt_format or dt_format == 'medium':
        from inphms import posix_to_ldml
        date_format = posix_to_ldml(lang.date_format, locale=locale)
        time_format = posix_to_ldml(lang.time_format, locale=locale)
        dt_format = '%s %s' % (date_format, time_format)

    # Babel allows to format datetime in a specific language without change locale
    # So month 1 = January in English, and janvier in French
    # Be aware that the default value for format is 'medium', instead of 'short'
    #     medium:  Jan 5, 2016, 10:20:31 PM |   5 janv. 2016 22:20:31
    #     short:   1/5/16, 10:20 PM         |   5/01/16 22:20
    # Formatting available here : http://babel.pocoo.org/en/latest/dates.html#date-fields
    return babel.dates.format_datetime(localized_datetime, dt_format, locale=locale)


def format_time(
    env: Environment,
    value: datetime.time | datetime.datetime | str,
    tz: str | t.Literal[False] = False,
    time_format: str = 'medium',
    lang_code: str | None = None,
) -> str:
    """ Format the given time (hour, minute and second) with the current user preference (language, format, ...)

        :param env:
        :param value: the time to format
        :type value: `datetime.time` instance. Could be timezoned to display tzinfo according to format (e.i.: 'full' format)
        :param tz: name of the timezone  in which the given datetime should be localized
        :param time_format: one of “full”, “long”, “medium”, or “short”, or a custom time pattern
        :param lang_code: ISO

        :rtype str
    """
    if not value:
        return ''

    if isinstance(value, datetime.time):
        localized_time = value
    else:
        if isinstance(value, str):
            from inphms.orm.fields import Datetime  # noqa: PLC0415
            value = Datetime.from_string(value)
        assert isinstance(value, datetime.datetime)
        tz_name = tz or env.user.tz or 'UTC'
        utc_datetime = pytz.utc.localize(value, is_dst=False)
        try:
            context_tz = pytz.timezone(tz_name)
            localized_time = utc_datetime.astimezone(context_tz).timetz()
        except Exception:
            localized_time = utc_datetime.timetz()

    lang = get_lang(env, lang_code)
    locale = babel_locale_parse(lang.code)
    if not time_format or time_format == 'medium':
        from inphms import posix_to_ldml
        time_format = posix_to_ldml(lang.time_format, locale=locale)

    return babel.dates.format_time(localized_time, format=time_format, locale=locale)


def formatLang(
    env: Environment,
    value: float | t.Literal[''],
    digits: int = 2,
    grouping: bool = True,
    dp: str | None = None,
    currency_obj: t.Any | None = None,
    rounding_method: t.Literal['HALF-UP', 'HALF-DOWN', 'HALF-EVEN', "UP", "DOWN"] = 'HALF-EVEN',
    rounding_unit: t.Literal['decimals', 'units', 'thousands', 'lakhs', 'millions'] = 'decimals',
) -> str:
    """
    This function will format a number `value` to the appropriate format of the language used.

    :param env: The environment.
    :param value: The value to be formatted.
    :param digits: The number of decimals digits.
    :param grouping: Usage of language grouping or not.
    :param dp: Name of the decimals precision to be used. This will override ``digits``
                   and ``currency_obj`` precision.
    :param currency_obj: Currency to be used. This will override ``digits`` precision.
    :param rounding_method: The rounding method to be used:
        **'HALF-UP'** will round to the closest number with ties going away from zero,
        **'HALF-DOWN'** will round to the closest number with ties going towards zero,
        **'HALF_EVEN'** will round to the closest number with ties going to the closest
        even number,
        **'UP'** will always round away from 0,
        **'DOWN'** will always round towards 0.
    :param rounding_unit: The rounding unit to be used:
        **decimals** will round to decimals with ``digits`` or ``dp`` precision,
        **units** will round to units without any decimals,
        **thousands** will round to thousands without any decimals,
        **lakhs** will round to lakhs without any decimals,
        **millions** will round to millions without any decimals.

    :returns: The value formatted.
    """
    # We don't want to return 0
    if value == '':
        return ''

    if rounding_unit == 'decimals':
        if dp:
            digits = env['decimal.precision'].precision_get(dp)
        elif currency_obj:
            digits = currency_obj.decimal_places
    else:
        digits = 0

    rounding_unit_mapping = {
        'decimals': 1,
        'thousands': 10**3,
        'lakhs': 10**5,
        'millions': 10**6,
        'units': 1,
    }

    value /= rounding_unit_mapping[rounding_unit]

    rounded_value = float_round(value, precision_digits=digits, rounding_method=rounding_method)
    lang = env['res.lang'].browse(get_lang(env).id)
    formatted_value = lang.format(f'%.{digits}f', rounded_value, grouping=grouping)

    if currency_obj and currency_obj.symbol:
        arguments = (formatted_value, NON_BREAKING_SPACE, currency_obj.symbol)

        return '%s%s%s' % (arguments if currency_obj.position == 'after' else arguments[::-1])

    return formatted_value
