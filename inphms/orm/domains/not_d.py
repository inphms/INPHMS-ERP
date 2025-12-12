from __future__ import annotations
import typing as t

from .optimization import OptimizationLevel
from .basedomain import Domain
from inphms.databases import SQL

if t.TYPE_CHECKING:
    from inphms.databases import Query
    from inphms.orm.models import BaseModel


class DomainNot(Domain):
    """Negation domain, contains a single child"""
    OPERATOR = '!'

    __slots__ = ('child',)
    child: Domain

    def __new__(cls, child: Domain):
        """Create a domain which is the inverse of the child."""
        self = object.__new__(cls)
        object.__setattr__(self, 'child', child)
        object.__setattr__(self, '_opt_level', OptimizationLevel.NONE)
        return self

    def __invert__(self):
        return self.child

    def __iter__(self):
        yield self.OPERATOR
        yield from self.child

    def iter_conditions(self):
        yield from self.child.iter_conditions()

    def map_conditions(self, function) -> Domain:
        return ~(self.child.map_conditions(function))

    def _optimize_step(self, model: BaseModel, level: OptimizationLevel) -> Domain:
        return self.child._optimize(model, level)._negate(model)

    def __eq__(self, other):
        return self is other or (isinstance(other, DomainNot) and self.child == other.child)

    def __hash__(self):
        return ~hash(self.child)

    def _as_predicate(self, records):
        predicate = self.child._as_predicate(records)
        return lambda rec: not predicate(rec)

    def _to_sql(self, model: BaseModel, alias: str, query: Query) -> SQL:
        condition = self.child._to_sql(model, alias, query)
        return SQL("(%s) IS NOT TRUE", condition)
