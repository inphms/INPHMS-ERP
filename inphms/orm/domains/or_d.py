from __future__ import annotations
import itertools

from inphms.tools import classproperty
from .bool import _FALSE_DOMAIN
from .nary import DomainNary
from inphms.databases import SQL


class DomainOr(DomainNary):
    """Domain: OR with multiple children"""
    __slots__ = ()
    OPERATOR = '|'
    OPERATOR_SQL = SQL(" OR ")
    ZERO = _FALSE_DOMAIN

    @classproperty
    def INVERSE(cls) -> type[DomainNary]:
        from .and_d import DomainAnd
        return DomainAnd

    def __or__(self, other):
        # simple optimization to append children
        if isinstance(other, DomainOr):
            return DomainOr(self.children + other.children)
        return super().__or__(other)

    def _as_predicate(self, records):
        # For the sake of performance, the list of predicates is generated
        # lazily with a generator, which is memoized with `itertools.tee`
        all_predicates = (child._as_predicate(records) for child in self.children)

        def or_predicate(record):
            nonlocal all_predicates
            all_predicates, predicates = itertools.tee(all_predicates)
            return any(pred(record) for pred in predicates)

        return or_predicate

