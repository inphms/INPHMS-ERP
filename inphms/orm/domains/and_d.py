from __future__ import annotations
import itertools

from inphms.tools import classproperty
from .bool import _TRUE_DOMAIN
from .nary import DomainNary
from inphms.databases import SQL


class DomainAnd(DomainNary):
    """Domain: AND with multiple children"""
    __slots__ = ()
    OPERATOR = '&'
    OPERATOR_SQL = SQL(" AND ")
    ZERO = _TRUE_DOMAIN

    @classproperty
    def INVERSE(cls) -> type[DomainNary]:
        from .or_d import DomainOr
        return DomainOr

    def __and__(self, other):
        # simple optimization to append children
        if isinstance(other, DomainAnd):
            return DomainAnd(self.children + other.children)
        return super().__and__(other)

    def _as_predicate(self, records):
        # For the sake of performance, the list of predicates is generated
        # lazily with a generator, which is memoized with `itertools.tee`
        all_predicates = (child._as_predicate(records) for child in self.children)

        def and_predicate(record):
            nonlocal all_predicates
            all_predicates, predicates = itertools.tee(all_predicates)
            return all(pred(record) for pred in predicates)

        return and_predicate
