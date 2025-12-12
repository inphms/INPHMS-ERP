from __future__ import annotations
import itertools
import typing as t
import operator as pyoperator

from collections.abc import Set as AbstractSet

from .numeric import NewId
from inphms.databases import SQL
from inphms.tools import SENTINEL

IdType = t.TypeAlias = t.Union[int, NewId, str]
if t.TYPE_CHECKING:
    from ..models import BaseModel


_global_seq = itertools.count()

from ..utils import SQL_OPERATORS

COLLECTION_TYPES = (list, tuple, AbstractSet)

COMPANY_DEPENDENT_FIELDS = (
    'char', 'float', 'boolean', 'integer', 'text', 'many2one', 'date', 'datetime', 'selection', 'html'
)

def resolve_mro(model: BaseModel, name: str, predicate) -> list[t.Any]:
    """ Return the list of successively overridden values of attribute ``name``
        in mro order on ``model`` that satisfy ``predicate``.  Model registry
        classes are ignored.
    """
    result = []
    for cls in model._model_classes__:
        value = cls.__dict__.get(name, SENTINEL)
        if value is SENTINEL:
            continue
        if not predicate(value):
            break
        result.append(value)
    return result


PYTHON_INEQUALITY_OPERATOR = {'<': pyoperator.lt, '>': pyoperator.gt, '<=': pyoperator.le, '>=': pyoperator.ge}