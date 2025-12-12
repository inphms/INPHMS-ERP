from __future__ import annotations
import typing as t
import itertools
import operator

from .optimization import OptimizationLevel
from .basedomain import Domain
from inphms.databases import SQL
from .bool import _FALSE_DOMAIN, DomainBool
from .condition import DomainCondition
from inphms.tools import classproperty
from .utils import NEGATIVE_CONDITION_OPERATORS, _MERGE_OPTIMIZATIONS

if t.TYPE_CHECKING:
    from inphms.databases import Query
    from inphms.orm.models import BaseModel
    from collections.abc import Iterable


class DomainNary(Domain):
    """Domain for a nary operator: AND or OR with multiple children"""
    OPERATOR: str
    OPERATOR_SQL: SQL = SQL(" ??? ")
    ZERO: DomainBool = _FALSE_DOMAIN  # default for lint checks

    __slots__ = ('children',)
    children: tuple[Domain, ...]

    def __new__(cls, children: tuple[Domain, ...]):
        """Create the n-ary domain with at least 2 conditions."""
        assert len(children) >= 2
        self = object.__new__(cls)
        object.__setattr__(self, 'children', children)
        object.__setattr__(self, '_opt_level', OptimizationLevel.NONE)
        return self

    @classmethod
    def apply(cls, items: Iterable[Domain]) -> Domain:
        """Return the result of combining AND/OR to a collection of domains."""
        children = cls._flatten(items)
        if len(children) == 1:
            return children[0]
        return cls(tuple(children))

    @classmethod
    def _flatten(cls, children: Iterable[Domain]) -> list[Domain]:
        """ Return an equivalent list of domains with respect to the boolean
            operation of the class (AND/OR).  Boolean subdomains are simplified,
            and subdomains of the same class are flattened into the list.
            The returned list is never empty.
        """
        result: list[Domain] = []
        for child in children:
            if isinstance(child, DomainBool):
                if child != cls.ZERO:
                    return [child]
            elif isinstance(child, cls):
                result.extend(child.children)  # same class, flatten
            else:
                result.append(child)
        return result or [cls.ZERO]

    def __iter__(self):
        yield from itertools.repeat(self.OPERATOR, len(self.children) - 1)
        for child in self.children:
            yield from child

    def __eq__(self, other):
        return self is other or (
            isinstance(other, DomainNary)
            and self.OPERATOR == other.OPERATOR
            and self.children == other.children
        )

    def __hash__(self):
        return hash(self.OPERATOR) ^ hash(self.children)

    @classproperty
    def INVERSE(cls) -> type[DomainNary]:
        """Return the inverted nary type, AND/OR"""
        raise NotImplementedError

    def __invert__(self):
        return self.INVERSE(tuple(~child for child in self.children))

    def _negate(self, model):
        return self.INVERSE(tuple(child._negate(model) for child in self.children))

    def iter_conditions(self):
        for child in self.children:
            yield from child.iter_conditions()

    def map_conditions(self, function) -> Domain:
        return self.apply(child.map_conditions(function) for child in self.children)

    def _optimize_step(self, model: BaseModel, level: OptimizationLevel) -> Domain:
        # optimize children
        children = self._flatten(child._optimize(model, level) for child in self.children)
        size = len(children)
        if size > 1:
            # sort children in order to ease their grouping by field and operator
            children.sort(key=_optimize_nary_sort_key)
            # run optimizations until some merge happens
            cls = type(self)
            for merge in _MERGE_OPTIMIZATIONS:
                children = merge(cls, children, model)
                if len(children) < size:
                    break
            else:
                # if no change, skip creation of a new object
                if len(self.children) == len(children) and all(map(operator.is_, self.children, children)):
                    return self
        return self.apply(children)

    def _to_sql(self, model: BaseModel, alias: str, query: Query) -> SQL:
        return SQL("(%s)", self.OPERATOR_SQL.join(
            c._to_sql(model, alias, query)
            for c in self.children
        ))


def _optimize_nary_sort_key(domain: Domain) -> tuple[str, str, str]:
    """ Sorting key for nary domains so that similar operators are grouped together.

        1. Field name (non-simple conditions are sorted at the end)
        2. Operator type (equality, inequality, existence, string comparison, other)
        3. Operator

        Sorting allows to have the same optimized domain for equivalent conditions.
        For debugging, it eases to find conditions on fields.
        The generated SQL will be ordered by field name so that database caching
        can be applied more frequently.
    """
    if isinstance(domain, DomainCondition):
        # group the same field and same operator together
        operator = domain.operator
        positive_op = NEGATIVE_CONDITION_OPERATORS.get(operator, operator)
        if positive_op == 'in':
            order = "0in"
        elif positive_op == 'any':
            order = "1any"
        elif positive_op == 'any!':
            order = "2any"
        elif positive_op.endswith('like'):
            order = "like"
        else:
            order = positive_op
        return domain.field_expr, order, operator
    elif hasattr(domain, 'OPERATOR') and isinstance(domain.OPERATOR, str):
        # in python; '~' > any letter
        return '~', '', domain.OPERATOR
    else:
        return '~', '~', domain.__class__.__name__
