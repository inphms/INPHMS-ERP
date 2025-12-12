from __future__ import annotations
import typing as t

from collections.abc import Mapping

if t.TYPE_CHECKING:
    from .basemodel import BaseModel

class RecordCache(Mapping[str, t.Any]):
    """ A mapping from field names to values, to read the cache of a record. """
    __slots__ = ['_record']

    def __init__(self, record: BaseModel):
        assert len(record) == 1, "Unexpected RecordCache(%s)" % record
        self._record = record

    def __contains__(self, name):
        """ Return whether `record` has a cached value for field ``name``. """
        record = self._record
        field = record._fields[name]
        return record.id in field._get_cache(record.env)

    def __getitem__(self, name):
        """ Return the cached value of field ``name`` for `record`. """
        record = self._record
        field = record._fields[name]
        return field._get_cache(record.env)[record.id]

    def __iter__(self):
        """ Iterate over the field names with a cached value. """
        record = self._record
        id_ = record.id
        env = record.env
        for name, field in record._fields.items():
            if id_ in field._get_cache(env):
                yield name

    def __len__(self):
        """ Return the number of fields with a cached value. """
        return sum(1 for name in self)
