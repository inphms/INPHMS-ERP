from __future__ import annotations
import typing as t
import babel
import datetime
import csv
import logging
import re

from operator import itemgetter
from babel import lists

from .filepaths import file_open

if t.TYPE_CHECKING:
    from inphms.modules import Environment
    from collections.abc import Iterable
    from typing import Literal

    from inphms.addons.base.models.res_lang import LangData

__all__ = ['format_list', 'babel_locale_parse', "get_lang", 'parse_date', "get_flag",
           "scan_languages", "py_to_js_locale"]

_logger = logging.getLogger(__name__)


XPG_LOCALE_RE = re.compile(
    r"""^
    ([a-z]+)      # language
    (_[A-Z\d]+)?  # maybe _territory
    # no support for .codeset (we don't use that in Inphms)
    (@.+)?        # maybe @modifier
    $""",
    re.VERBOSE,
)


def get_flag(country_code: str) -> str:
    """Get the emoji representing the flag linked to the country code.

    This emoji is composed of the two regional indicator emoji of the country code.
    """
    return "".join(chr(int(f"1f1{ord(c)+165:02x}", base=16)) for c in country_code)


def get_lang(env: Environment, lang_code: str | None = None) -> LangData:
    """
    Retrieve the first lang object installed, by checking the parameter lang_code,
    the context and then the company. If no lang is installed from those variables,
    fallback on english or on the first lang installed in the system.

    :param env:
    :param str lang_code: the locale (i.e. en_US)
    :return LangData: the first lang found that is installed on the system.
    """
    langs = [code for code, _ in env['res.lang'].get_installed()]
    lang = 'en_US' if 'en_US' in langs else langs[0]
    if lang_code and lang_code in langs:
        lang = lang_code
    elif (context_lang := env.context.get('lang')) in langs:
        lang = context_lang
    elif (company_lang := env.user.with_context(lang='en_US').company_id.partner_id.lang) in langs:
        lang = company_lang
    return env['res.lang']._get_data(code=lang)


def babel_locale_parse(lang_code: str | None) -> babel.Locale:
    if lang_code:
        try:
            return babel.Locale.parse(lang_code)
        except Exception:  # noqa: BLE001
            _logger.warning(f"import error, {lang_code}")
            pass
    try:
        return babel.Locale.default()
    except Exception:  # noqa: BLE001
        return babel.Locale.parse("en_US")


def format_list(
    env: Environment,
    lst: Iterable,
    style: Literal["standard", "standard-short", "or", "or-short", "unit", "unit-short", "unit-narrow"] = "standard",
    lang_code: str | None = None,
) -> str:
    """
        Format the items in `lst` as a list in a locale-dependent manner with the chosen style.

        The available styles are defined by babel according to the Unicode TR35-49 spec:
        * standard:
        A typical 'and' list for arbitrary placeholders.
        e.g. "January, February, and March"
        * standard-short:
        A short version of an 'and' list, suitable for use with short or abbreviated placeholder values.
        e.g. "Jan., Feb., and Mar."
        * or:
        A typical 'or' list for arbitrary placeholders.
        e.g. "January, February, or March"
        * or-short:
        A short version of an 'or' list.
        e.g. "Jan., Feb., or Mar."
        * unit:
        A list suitable for wide units.
        e.g. "3 feet, 7 inches"
        * unit-short:
        A list suitable for short units
        e.g. "3 ft, 7 in"
        * unit-narrow:
        A list suitable for narrow units, where space on the screen is very limited.
        e.g. "3′ 7″"

        See https://www.unicode.org/reports/tr35/tr35-49/tr35-general.html#ListPatterns for more details.

        :param env: the current environment.
        :param lst: the iterable of items to format into a list.
        :param style: the style to format the list with.
        :param lang_code: the locale (i.e. en_US).
        :return: the formatted list.
    """
    locale = babel_locale_parse(lang_code or get_lang(env).code)
    # Some styles could be unavailable for the chosen locale
    if style not in locale.list_patterns:
        style = "standard"
    return lists.format_list([str(el) for el in lst], style, locale)


def py_to_js_locale(locale: str) -> str:
    """
    Converts a locale from Python to JavaScript format.

    Most of the time the conversion is simply to replace _ with -.
    Example: fr_BE → fr-BE

    Exception: Serbian can be written in both Latin and Cyrillic scripts
    interchangeably, therefore its locale includes a special modifier
    to indicate which script to use.
    Example: sr@latin → sr-Latn

    BCP 47 (JS):
        language[-extlang][-script][-region][-variant][-extension][-privateuse]
        https://www.ietf.org/rfc/rfc5646.txt
    XPG syntax (Python):
        language[_territory][.codeset][@modifier]
        https://www.gnu.org/software/libc/manual/html_node/Locale-Names.html

    :param locale: The locale formatted for use on the Python-side.
    :return: The locale formatted for use on the JavaScript-side.
    """
    match_ = XPG_LOCALE_RE.match(locale)
    if not match_:
        return locale
    language, territory, modifier = match_.groups()
    subtags = [language]
    if modifier == "@Cyrl":
        subtags.append("Cyrl")
    elif modifier == "@latin":
        subtags.append("Latn")
    if territory:
        subtags.append(territory.removeprefix("_"))
    return "-".join(subtags)


def parse_date(env: Environment, value: str, lang_code: str | None = None) -> datetime.date | str:
    """
        Parse the date from a given format. If it is not a valid format for the
        localization, return the original string.

        :param env: an environment.
        :param string value: the date to parse.
        :param string lang_code: the lang code, if not specified it is extracted from the
            environment context.
        :return: date object from the localized string
        :rtype: datetime.date
    """
    lang = get_lang(env, lang_code)
    locale = babel_locale_parse(lang.code)
    try:
        return babel.dates.parse_date(value, locale=locale)
    except:
        return value


def scan_languages() -> list[tuple[str, str]]:
    """ Returns all languages supported by OpenERP for translation

    :returns: a list of (lang_code, lang_name) pairs
    :rtype: [(str, unicode)]
    """
    try:
        # read (code, name) from languages in base/data/res.lang.csv
        with file_open('base/data/res.lang.csv') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            fields = next(reader)
            code_index = fields.index("code")
            name_index = fields.index("name")
            result = [
                (row[code_index], row[name_index])
                for row in reader
            ]
    except Exception:
        _logger.error("Could not read res.lang.csv")
        result = []

    return sorted(result or [('en_US', u'English')], key=itemgetter(1))
