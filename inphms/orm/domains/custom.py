from __future__ import annotations
import typing as t

from .optimization import OptimizationLevel
from .basedomain import Domain
from .condition import DomainCondition
from inphms.databases import SQL

if t.TYPE_CHECKING:
    from inphms.databases import Query
    from inphms.orm.models import BaseModel
    from collections.abc import Callable


class DomainCustom(Domain):
    """Domain condition that generates directly SQL and possibly a ``filtered`` predicate."""
    __slots__ = ('_filtered', '_sql')

    _filtered: Callable[[BaseModel], bool] | None
    _sql: Callable[[BaseModel, str, Query], SQL]

    def __new__(
        cls,
        sql: Callable[[BaseModel, str, Query], SQL],
        filtered: Callable[[BaseModel], bool] | None = None,
    ):
        """Create a new domain.

        :param to_sql: callable(model, alias, query) that implements ``_to_sql``
                       which is used to generate the query for searching
        :param predicate: callable(record) that checks whether a record is kept
                          when filtering (``Model.filtered``)
        """
        self = object.__new__(cls)
        object.__setattr__(self, '_sql', sql)
        object.__setattr__(self, '_filtered', filtered)
        object.__setattr__(self, '_opt_level', OptimizationLevel.FULL)
        return self

    def _as_predicate(self, records):
        if self._filtered is not None:
            return self._filtered
        # by default, run the SQL query
        query = records._search(DomainCondition('id', 'in', records.ids) & self, order='id')
        return DomainCondition('id', 'any', query)._as_predicate(records)

    def __eq__(self, other):
        return (
            isinstance(other, DomainCustom)
            and self._sql == other._sql
            and self._filtered == other._filtered
        )

    def __hash__(self):
        return hash(self._sql)

    def __iter__(self):
        yield self

    def _to_sql(self, model: BaseModel, alias: str, query: Query) -> SQL:
        return self._sql(model, alias, query)
