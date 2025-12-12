# ruff: noqa

from .base import Base, Unknown

from .model import IrModel
from .data import IrModelData
from .field import IrModelFields
from .fieldsel import IrModelFieldsSelection
from .inherit import IrModelInherit
from .constraint import IrModelConstraint
from .acc import IrModelAccess
from .relation import IrModelRelation

from .utils import MODULE_UNINSTALL_FLAG
