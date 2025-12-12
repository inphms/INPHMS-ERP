from __future__ import annotations
import typing as t

from inphms.databases import sqlutils as sql

if t.TYPE_CHECKING:
    from ..models import BaseModel
    from inphms.modules import Registry
    from .utils import ConstraintMessageType


class TableObject:
    """ Declares a SQL object related to the model.

        The identifier of the SQL object will be "{model._table}_{name}".
    """
    name: str
    message: ConstraintMessageType = ''
    _module: str = ''

    def __init__(self):
        """Abstract SQL object"""
        # to avoid confusion: name is unique inside the model, full_name is in the database
        self.name = ''

    def __set_name__(self, owner, name):
        # database objects should be private member fo the class:
        # first of all, you should not need to access them from any model
        # and this avoid having them in the middle of the fields when listing members
        assert name.startswith('_'), "Names of SQL objects in a model must start with '_'"
        assert not name.startswith(f"_{owner.__name__}__"), "Names of SQL objects must not be mangled"
        self.name = name[1:]
        if getattr(owner, 'pool', None) is None:  # models.is_model_definition(owner)
            # only for fields on definition classes, not registry classes
            self._module = owner._module
            owner._table_object_definitions.append(self)

    def get_definition(self, registry: Registry) -> str:
        raise NotImplementedError

    def full_name(self, model: BaseModel) -> str:
        assert self.name, f"The table object is not named ({self.definition})"
        name = f"{model._table}_{self.name}"
        return sql.make_identifier(name)

    def get_error_message(self, model: BaseModel, diagnostics=None) -> str:
        """Build an error message for the object/constraint.

            :param model: Optional model on which the constraint is defined
            :param diagnostics: Optional diagnostics from the raised exception
            :return: Translated error for the user
        """
        message = self.message
        if callable(message):
            return message(model.env, diagnostics)
        return message

    def apply_to_database(self, model: BaseModel):
        raise NotImplementedError

    def __str__(self) -> str:
        return f"({self.name!r}={self.definition!r}, {self.message!r})"
