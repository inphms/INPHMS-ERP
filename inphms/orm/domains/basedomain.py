from __future__ import annotations
import typing as t
import types

from .optimization import OptimizationLevel
from .utils import _TRUE_LEAF, _FALSE_LEAF, INTERNAL_CONDITION_OPERATORS, \
    NEGATIVE_CONDITION_OPERATORS, MAX_OPTIMIZE_ITERATIONS
from inphms.tools import classproperty
from inphms.databases import Query, SQL

if t.TYPE_CHECKING:
    from collections.abc import Iterable, Callable
    from ..models import BaseModel
    from .custom import DomainCustom
    from .condition import DomainCondition

    M = t.TypeVar('M', bound=BaseModel)

class Domain:
    """ Representation of a domain as an AST.
    """
    # Domain is an abstract class (ABC), but not marked as such
    # because we overwrite __new__ so typechecking for abstractmethod is incorrect.
    # We do this so that we can use the Domain as both a factory for multiple
    # types of domains, while still having `isinstance` working for it.
    __slots__ = ('_opt_level',)
    _opt_level: OptimizationLevel

    def __new__(cls, *args, internal: bool = False):
        """ Build a domain AST.

            ```
            Domain([('a', '=', 5), ('b', '=', 8)])
            Domain('a', '=', 5) & Domain('b', '=', 8)
            Domain.AND([Domain('a', '=', 5), *other_domains, Domain.TRUE])
            ```

            If we have one argument, it is a `Domain`, or a list representation, or a bool.
            In case we have multiple ones, there must be 3 of them:
            a field (str), the operator (str) and a value for the condition.

            By default, the special operators ``'any!'`` and ``'not any!'`` are
            allowed in domain conditions (``Domain('a', 'any!', dom)``) but not in
            domain lists (``Domain([('a', 'any!', dom)])``).
        """
        from .bool import _TRUE_DOMAIN, _FALSE_DOMAIN
        if len(args) > 1:
            if isinstance(args[0], str):
                from .condition import DomainCondition
                return DomainCondition(*args).checked()
            # special cases like True/False constants
            
            if args == _TRUE_LEAF:
                return _TRUE_DOMAIN
            if args == _FALSE_LEAF:
                return _FALSE_DOMAIN
            raise TypeError(f"Domain() invalid arguments: {args!r}")

        arg = args[0]
        if isinstance(arg, Domain):
            return arg
        if arg is True or arg == []:
            return _TRUE_DOMAIN
        if arg is False:
            return _FALSE_DOMAIN
        if arg is NotImplemented:
            raise NotImplementedError

        # parse as a list
        # perf: do this inside __new__ to avoid calling function that return
        # a Domain which would call implicitly __init__
        if not isinstance(arg, (list, tuple)):
            raise TypeError(f"Domain() invalid argument type for domain: {arg!r}")
        stack: list[Domain] = []
        try:
            from .and_d import DomainAnd
            from .or_d import DomainOr
            from .not_d import DomainNot
            for item in reversed(arg):
                if isinstance(item, (tuple, list)) and len(item) == 3:
                    if internal:
                        # process subdomains when processing internal operators
                        if item[1] in ('any', 'any!', 'not any', 'not any!') and isinstance(item[2], (list, tuple)):
                            item = (item[0], item[1], Domain(item[2], internal=True))
                    elif item[1] in INTERNAL_CONDITION_OPERATORS:
                        # internal operators are not accepted
                        raise ValueError(f"Domain() invalid item in domain: {item!r}")
                    stack.append(Domain(*item))
                elif item == DomainAnd.OPERATOR:
                    stack.append(stack.pop() & stack.pop())
                elif item == DomainOr.OPERATOR:
                    stack.append(stack.pop() | stack.pop())
                elif item == DomainNot.OPERATOR:
                    stack.append(~stack.pop())
                elif isinstance(item, Domain):
                    stack.append(item)
                else:
                    raise ValueError(f"Domain() invalid item in domain: {item!r}")
            # keep the order and simplify already
            if len(stack) == 1:
                return stack[0]
            return Domain.AND(reversed(stack))
        except IndexError:
            raise ValueError(f"Domain() malformed domain {arg!r}")

    @classproperty
    def TRUE(cls) -> Domain:
        from .bool import _TRUE_DOMAIN
        return _TRUE_DOMAIN

    @classproperty
    def FALSE(cls) -> Domain:
        from .bool import _FALSE_DOMAIN
        return _FALSE_DOMAIN

    NEGATIVE_OPERATORS = types.MappingProxyType(NEGATIVE_CONDITION_OPERATORS)

    @staticmethod
    def custom(
        *,
        to_sql: Callable[[BaseModel, str, Query], SQL],
        predicate: Callable[[BaseModel], bool] | None = None,
    ) -> DomainCustom:
        """Create a custom domain.

            :param to_sql: callable(model, alias, query) that returns the SQL
            :param predicate: callable(record) that checks whether a record is kept
                            when filtering
        """
        from .custom import DomainCustom
        return DomainCustom(to_sql, predicate)

    @staticmethod
    def AND(items: Iterable) -> Domain:
        """Build the conjuction of domains: (item1 AND item2 AND ...)"""
        from .and_d import DomainAnd
        return DomainAnd.apply(Domain(item) for item in items)

    @staticmethod
    def OR(items: Iterable) -> Domain:
        """Build the disjuction of domains: (item1 OR item2 OR ...)"""
        from .or_d import DomainOr
        return DomainOr.apply(Domain(item) for item in items)

    def __setattr__(self, name, value):
        raise TypeError("Domain objects are immutable")

    def __delattr__(self, name):
        raise TypeError("Domain objects are immutable")

    def __and__(self, other):
        """Domain & Domain"""
        if isinstance(other, Domain):
            from .and_d import DomainAnd
            return DomainAnd.apply([self, other])
        return NotImplemented

    def __or__(self, other):
        """Domain | Domain"""
        if isinstance(other, Domain):
            from .or_d import DomainOr
            return DomainOr.apply([self, other])
        return NotImplemented

    def __invert__(self):
        """~Domain"""
        from .not_d import DomainNot
        return DomainNot(self)

    def _negate(self, model: BaseModel) -> Domain:
        """Apply (propagate) negation onto this domain. """
        return ~self

    def __add__(self, other):
        """ Domain + [...]

            For backward-compatibility of domain composition.
            Concatenate as lists.
            If we have two domains, equivalent to '&'.
        """
        # TODO deprecate this possibility so that users combine domains correctly
        if isinstance(other, Domain):
            return self & other
        if not isinstance(other, list):
            raise TypeError('Domain() can concatenate only lists')
        return list(self) + other

    def __radd__(self, other):
        """Commutative definition of *+*"""
        # TODO deprecate this possibility so that users combine domains correctly
        # we are pre-pending, return a list
        # because the result may not be normalized
        return other + list(self)

    def __bool__(self):
        """Indicate that the domain is not true.

        For backward-compatibility, only the domain [] was False. Which means
        that the TRUE domain is falsy and others are truthy.
        """
        # TODO deprecate this usage, we have is_true() and is_false()
        # warnings.warn("Do not use bool() on Domain, use is_true() or is_false() instead", DeprecationWarning)
        return not self.is_true()

    def __eq__(self, other):
        raise NotImplementedError

    def __hash__(self):
        raise NotImplementedError

    def __iter__(self):
        """For-backward compatibility, return the polish-notation domain list"""
        yield from ()
        raise NotImplementedError

    def __reversed__(self):
        """For-backward compatibility, reversed iter"""
        return reversed(list(self))

    def __repr__(self) -> str:
        # return representation of the object as the old-style list
        return repr(list(self))

    def is_true(self) -> bool:
        """Return whether self is TRUE"""
        return False

    def is_false(self) -> bool:
        """Return whether self is FALSE"""
        return False

    def iter_conditions(self) -> Iterable[DomainCondition]:
        """Yield simple conditions of the domain"""
        yield from ()

    def map_conditions(self, function: Callable[[DomainCondition], Domain]) -> Domain:
        """Map a function to each condition and return the combined result"""
        return self

    def validate(self, model: BaseModel) -> None:
        """Validates that the current domain is correct or raises an exception"""
        # just execute the optimization code that goes through all the fields
        self._optimize(model, OptimizationLevel.FULL)

    def _as_predicate(self, records: M) -> Callable[[M], bool]:
        """Return a predicate function from the domain (bound to records).
        The predicate function return whether its argument (a single record)
        satisfies the domain.

        This is used to implement ``Model.filtered_domain``.
        """
        raise NotImplementedError

    def optimize(self, model: BaseModel) -> Domain:
        """Perform optimizations of the node given a model.

        It is a pre-processing step to rewrite the domain into a logically
        equivalent domain that is a more canonical representation of the
        predicate. Multiple conditions can be merged together.

        It applies basic optimizations only. Those are transaction-independent;
        they only depend on the model's fields definitions. No model-specific
        override is used, and the resulting domain may be reused in another
        transaction without semantic impact.
        The model's fields are used to validate conditions and apply
        type-dependent optimizations. This optimization level may be useful to
        simplify a domain that is sent to the client-side, thereby reducing its
        payload/complexity.
        """
        return self._optimize(model, OptimizationLevel.BASIC)

    def optimize_full(self, model: BaseModel) -> Domain:
        """Perform optimizations of the node given a model.

        Basic and advanced optimizations are applied.
        Advanced optimizations may rely on model specific overrides
        (search methods of fields, etc.) and the semantic equivalence is only
        guaranteed at the given point in a transaction. We resolve inherited
        and non-stored fields (using their search method) to transform the
        conditions.
        """
        return self._optimize(model, OptimizationLevel.FULL)

    @t.final
    def _optimize(self, model: BaseModel, level: OptimizationLevel) -> Domain:
        """Perform optimizations of the node given a model.

        Reach a fixed-point by applying the optimizations for the next level
        on the node until we reach a stable node at the given level.
        """
        domain, previous, count = self, None, 0
        while domain._opt_level < level:
            if (count := count + 1) > MAX_OPTIMIZE_ITERATIONS:
                raise RecursionError("Domain.optimize: too many loops")
            next_level = domain._opt_level.next_level
            previous, domain = domain, domain._optimize_step(model, next_level)
            # set the optimization level if necessary (unlike DomainBool, for instance)
            if domain == previous and domain._opt_level < next_level:
                object.__setattr__(domain, '_opt_level', next_level)  # noqa: PLC2801
        return domain

    def _optimize_step(self, model: BaseModel, level: OptimizationLevel) -> Domain:
        """Implementation of domain for one level of optimizations."""
        return self

    def _to_sql(self, model: BaseModel, alias: str, query: Query) -> SQL:
        """Build the SQL to inject into the query.  The domain should be optimized first."""
        raise NotImplementedError
