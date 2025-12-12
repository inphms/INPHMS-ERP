from __future__ import annotations
import typing as t

from ..field import Field
from inphms.databases import SQL

if t.TYPE_CHECKING:
    from ...models import BaseModel
    from inphms.databases import Query


class Boolean(Field[bool]):
    """ Encapsulates a :class:`bool`. """
    type = 'boolean'
    _column_type = ('bool', 'bool')
    falsy_value = False

    def convert_to_column(self, value, record, values=None, validate=True):
        return bool(value)

    def convert_to_cache(self, value, record, validate=True):
        return bool(value)

    def convert_to_export(self, value, record):
        return bool(value)

    def _condition_to_sql(self, field_expr: str, operator: str, value, model: BaseModel, alias: str, query: Query) -> SQL:
        if operator not in ('in', 'not in'):
            return super()._condition_to_sql(field_expr, operator, value, model, alias, query)

        # get field and check access
        sql_field = model._field_to_sql(alias, field_expr, query)

        # express all conditions as (field_expr, 'in', possible_values)
        possible_values = (
            {bool(v) for v in value} if operator == 'in' else
            {True, False} - {bool(v) for v in value}  # operator == 'not in'
        )
        if len(possible_values) != 1:
            return SQL("TRUE") if possible_values else SQL("FALSE")
        is_true = True in possible_values
        return SQL("%s IS TRUE", sql_field) if is_true else SQL("%s IS NOT TRUE", sql_field)
