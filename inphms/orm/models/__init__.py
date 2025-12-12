# ruff: noqa

from .metamodel import MetaModel
from .basemodel import BaseModel
from .model import Model, AbstractModel
from .utils import *

import collections.abc


collections.abc.Set.register(BaseModel)
# not exactly true as BaseModel doesn't have index or count
collections.abc.Sequence.register(BaseModel)


from ..table_objects import Constraint, Index, UniqueIndex
from .transient import TransientModel