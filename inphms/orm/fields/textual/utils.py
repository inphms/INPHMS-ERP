from __future__ import annotations
import collections
import typing as t

from inphms.tools import SENTINEL

if t.TYPE_CHECKING:
    from .basestring import BaseString


class LangProxyDict(collections.abc.MutableMapping):
    """A view on a dict[id, dict[lang, value]] that maps id to value given a
    fixed language."""
    __slots__ = ('_cache', '_field', '_lang')

    def __init__(self, field: BaseString, cache: dict, lang: str):
        super().__init__()
        self._field = field
        self._cache = cache
        self._lang = lang

    def get(self, key, default=None):
        # just for performance
        vals = self._cache.get(key, SENTINEL)
        if vals is SENTINEL:
            return default
        if vals is None:
            return None
        if not (self._field.compute or (self._field.store and (key or key.origin))):
            # the field's value is neither computed, nor in database
            # (non-stored field or new record without origin), so fallback on
            # its 'en_US' value in cache
            return vals.get(self._lang, vals.get('en_US', default))
        return vals.get(self._lang, default)

    def __getitem__(self, key):
        vals = self._cache[key]
        if vals is None:
            return None
        if not (self._field.compute or (self._field.store and (key or key.origin))):
            # the field's value is neither computed, nor in database
            # (non-stored field or new record without origin), so fallback on
            # its 'en_US' value in cache
            return vals.get(self._lang, vals.get('en_US'))
        return vals[self._lang]

    def __setitem__(self, key, value):
        if value is None:
            self._cache[key] = None
            return
        vals = self._cache.get(key)
        if vals is None:
            # key is not in cache, or {key: None} is in cache
            self._cache[key] = vals = {self._lang: value}
        else:
            vals[self._lang] = value
        if not (self._field.compute or (self._field.store and (key or key.origin))):
            # the field's value is neither computed, nor in database
            # (non-stored field or new record without origin), so the cache
            # must contain the fallback 'en_US' value for other languages
            vals.setdefault('en_US', value)

    def __delitem__(self, key):
        vals = self._cache.get(key)
        if vals:
            vals.pop(self._lang, None)

    def __iter__(self):
        for key, vals in self._cache.items():
            if vals is None or self._lang in vals:
                yield key

    def __len__(self):
        return sum(1 for _ in self)

    def clear(self):
        for vals in self._cache.values():
            if vals:
                vals.pop(self._lang, None)

    def __repr__(self):
        return f"<LangProxyDict lang={self._lang!r} size={len(self._cache)} at {hex(id(self))}>"
