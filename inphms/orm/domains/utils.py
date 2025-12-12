from __future__ import annotations
import logging
import typing as t
import collections

from .optimization import OptimizationLevel

_logger = logging.getLogger("inphms.domains")

_TRUE_LEAF = (1, '=', 1)
_FALSE_LEAF = (0, '=', 1)

INTERNAL_CONDITION_OPERATORS = frozenset(('any!', 'not any!'))
NEGATIVE_CONDITION_OPERATORS = {
    'not any': 'any',
    'not any!': 'any!',
    'not in': 'in',
    'not like': 'like',
    'not ilike': 'ilike',
    'not =like': '=like',
    'not =ilike': '=ilike',
    '!=': '=',
    '<>': '=',
}
"""A subset of operators with a 'negative' semantic, mapping to the 'positive' operator."""

STANDARD_CONDITION_OPERATORS = frozenset([
    'any', 'not any',
    'any!', 'not any!',
    'in', 'not in',
    '<', '>', '<=', '>=',
    'like', 'not like',
    'ilike', 'not ilike',
    '=like', 'not =like',
    '=ilike', 'not =ilike',
])
"""List of standard operators for conditions.
This should be supported in the framework at all levels.

- `any` works for relational fields and `id` to check if a record matches
  the condition
  - if value is SQL or Query, see `any!`
  - if bypass_search_access is set on the field, see `any!`
  - if value is a Domain for a many2one (or `id`),
    _search with active_test=False
  - if value is a Domain for a x2many,
    _search on the comodel of the field (with its context)
- `any!` works like `any` but bypass adding record rules on the comodel
- `in` for equality checks where the given value is a collection of values
  - the collection is transformed into OrderedSet
  - False value indicates that the value is *not set*
  - for relational fields
    - if int, bypass record rules
    - if str, search using display_name of the model
  - the value should have the type of the field
  - SQL type is always accepted
- `<`, `>`, ... inequality checks, similar behaviour to `in` with a single value
- string pattern comparison
  - `=like` case-sensitive compare to a string using SQL like semantics
  - `=ilike` case-insensitive with `unaccent` comparison to a string
  - `like`, `ilike` behave like the preceding methods, but add a wildcards
    around the value
"""
CONDITION_OPERATORS = set(STANDARD_CONDITION_OPERATORS)  # modifiable (for optimizations only)
"""
List of available operators for conditions.
The non-standard operators can be reduced to standard operators by using the
optimization function. See the respective optimization functions for the
details.
"""

MAX_OPTIMIZE_ITERATIONS = 1000

if t.TYPE_CHECKING:
    from collections.abc import Callable
    from .condition import DomainCondition
    from .basedomain import Domain
    from .nary import DomainNary
    from inphms.orm.models import BaseModel

    ConditionOptimization = Callable[[DomainCondition, BaseModel], Domain]
    MergeOptimization = Callable[[type[DomainNary], list[Domain], BaseModel], list[Domain]]


_OPTIMIZATIONS_FOR: dict[OptimizationLevel, dict[str, list[ConditionOptimization]]] = {
    level: collections.defaultdict(list) for level in OptimizationLevel if level != OptimizationLevel.NONE}
_MERGE_OPTIMIZATIONS: list[MergeOptimization] = list()


# negations for operators (used in DomainNot)
_INVERSE_OPERATOR = {
    # from NEGATIVE_CONDITION_OPERATORS
    'not any': 'any',
    'not any!': 'any!',
    'not in': 'in',
    'not like': 'like',
    'not ilike': 'ilike',
    'not =like': '=like',
    'not =ilike': '=ilike',
    '!=': '=',
    '<>': '=',
    # positive to negative
    'any': 'not any',
    'any!': 'not any!',
    'in': 'not in',
    'like': 'not like',
    'ilike': 'not ilike',
    '=like': 'not =like',
    '=ilike': 'not =ilike',
    '=': '!=',
}
"""Dict to find the inverses of the operators."""
_INVERSE_INEQUALITY = {
    '<': '>=',
    '>': '<=',
    '>=': '<',
    '<=': '>',
}
""" Dict to find the inverse of inequality operators.
Handled differently because of null values."""



