from __future__ import annotations
import typing as t

from ..field import Field
from ..utils import IdType
from inphms.databases import SQL

if t.TYPE_CHECKING:
    from inphms.orm.models import BaseModel

class Id(Field[IdType | t.Literal[False]]):
    """ Special case for field 'id'. """
    # Note: This field type is not necessarily an integer!
    type = 'integer'  # note this conflicts with Integer
    column_type = ('int4', 'int4')

    string = 'ID'
    store = True
    readonly = True
    prefetch = False

    def update_db(self, model, columns):
        pass                            # this column is created with the table

    def __get__(self, record, owner=None):
        if record is None:
            return self         # the field is accessed through the class owner

        # the code below is written to make record.id as quick as possible
        ids = record._ids
        size = len(ids)
        if size == 0:
            return False
        elif size == 1:
            return ids[0]
        raise ValueError("Expected singleton: %s" % record)

    def __set__(self, record, value):
        raise TypeError("field 'id' cannot be assigned")

    def convert_to_column(self, value, record, values=None, validate=True):
        return value

    def to_sql(self, model: BaseModel, alias: str) -> SQL:
        # do not flush, just return the identifier
        assert self.store, 'id field must be stored'
        # id is never flushed
        return SQL.identifier(alias, self.name)

    def expression_getter(self, field_expr):
        if field_expr != 'id.origin':
            return super().expression_getter(field_expr)

        def getter(record):
            return (id_ := record._ids[0]) or getattr(id_, 'origin', None) or False

        return getter
