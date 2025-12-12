from __future__ import annotations

from markupsafe import Markup, escape_silent
from inphms.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

def nl2br(string: str) -> Markup:
    """ Converts newlines to HTML linebreaks in ``string`` after HTML-escaping
    it.
    """
    return escape_silent(string).replace('\n', Markup('<br>\n'))

def nl2br_enclose(string: str, enclosure_tag: str = 'div') -> Markup:
    """ Like nl2br, but returns enclosed Markup allowing to better manipulate
    trusted and untrusted content. New lines added by use are trusted, other
    content is escaped. """
    return Markup('<{enclosure_tag}>{converted}</{enclosure_tag}>').format(
        enclosure_tag=enclosure_tag,
        converted=nl2br(string),
    )


TIMEDELTA_UNITS = (
    ('year',   _lt('year'),   3600 * 24 * 365),
    ('month',  _lt('month'),  3600 * 24 * 30),
    ('week',   _lt('week'),   3600 * 24 * 7),
    ('day',    _lt('day'),    3600 * 24),
    ('hour',   _lt('hour'),   3600),
    ('minute', _lt('minute'), 60),
    ('second', _lt('second'), 1)
)
