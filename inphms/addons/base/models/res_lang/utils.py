from __future__ import annotations
import re
import typing as t

from inphms.tools import ReadonlyDict


def split(l, counts):
    """
    >>> split("hello world", [])
    ['hello world']
    >>> split("hello world", [1])
    ['h', 'ello world']
    >>> split("hello world", [2])
    ['he', 'llo world']
    >>> split("hello world", [2,3])
    ['he', 'llo', ' world']
    >>> split("hello world", [2,3,0])
    ['he', 'llo', ' wo', 'rld']
    >>> split("hello world", [2,-1,3])
    ['he', 'llo world']
    """
    res = []
    saved_count = len(l) # count to use when encoutering a zero
    for count in counts:
        if not l:
            break
        if count == -1:
            break
        if count == 0:
            while l:
                res.append(l[:saved_count])
                l = l[saved_count:]
            break
        res.append(l[:count])
        l = l[count:]
        saved_count = count
    if l:
        res.append(l)
    return res

intersperse_pat = re.compile('([^0-9]*)([^ ]*)(.*)')
def intersperse(string, counts, separator=''):
    """

    See the asserts below for examples.

    """
    left, rest, right = intersperse_pat.match(string).groups()
    def reverse(s): return s[::-1]
    splits = split(reverse(rest), counts)
    res = separator.join(reverse(s) for s in reverse(splits))
    return left + res + right, len(splits) > 0 and len(splits) -1 or 0


################
# CLASS HELPER #
################

class LangData(ReadonlyDict):
    """ A ``dict``-like class which can access field value like a ``res.lang`` record.
    Note: This data class cannot store data for fields with the same name as
    ``dict`` methods, like ``dict.keys``.
    """
    __slots__ = ()

    def __bool__(self) -> bool:
        return bool(self.id)

    def __getattr__(self, name: str) -> t.Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError


class LangDataDict(ReadonlyDict):
    """ A ``dict`` of :class:`LangData` objects indexed by some key, which returns
    a special dummy :class:`LangData` for missing keys.
    """
    __slots__ = ()

    def __getitem__(self, key: t.Any) -> LangData:
        try:
            return self._data__[key]
        except KeyError:
            some_lang = next(iter(self.values()))  # should have at least one active language
            return LangData(dict.fromkeys(some_lang, False))
