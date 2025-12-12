from __future__ import annotations
import typing as t

from collections.abc import Reversible
from inphms.tools import unique

if t.TYPE_CHECKING:
    from inphms.orm.models import BaseModel
    from inphms.orm.fields import Many2one
    from .baserelationalmulti import _RelationalMulti


class PrefetchMany2one(Reversible):
    """ Iterable for the values of a many2one field on the prefetch set of a given record. """
    __slots__ = ('field', 'record')

    def __init__(self, record: BaseModel, field: Many2one):
        self.record = record
        self.field = field

    def __iter__(self):
        field_cache = self.field._get_cache(self.record.env)
        return unique(
            coid for id_ in self.record._prefetch_ids
            if (coid := field_cache.get(id_)) is not None
        )

    def __reversed__(self):
        field_cache = self.field._get_cache(self.record.env)
        return unique(
            coid for id_ in reversed(self.record._prefetch_ids)
            if (coid := field_cache.get(id_)) is not None
        )


class PrefetchX2many(Reversible):
    """ Iterable for the values of an x2many field on the prefetch set of a given record. """
    __slots__ = ('field', 'record')

    def __init__(self, record: BaseModel, field: _RelationalMulti):
        self.record = record
        self.field = field

    def __iter__(self):
        field_cache = self.field._get_cache(self.record.env)
        return unique(
            coid
            for id_ in self.record._prefetch_ids
            for coid in field_cache.get(id_, ())
        )

    def __reversed__(self):
        field_cache = self.field._get_cache(self.record.env)
        return unique(
            coid
            for id_ in reversed(self.record._prefetch_ids)
            for coid in field_cache.get(id_, ())
        )
