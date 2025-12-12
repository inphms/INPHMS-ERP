from __future__ import annotations
import typing as t

from . import TableObject
from inphms.databases import sqlutils as sql

if t.TYPE_CHECKING:
    from ..models import BaseModel
    from inphms.modules import Registry
    from .utils import ConstraintMessageType

class Constraint(TableObject):
    """ SQL table constraint.

        The definition of the constraint is used to `ADD CONSTRAINT` on the table.
    """

    def __init__(
        self,
        definition: str,
        message: ConstraintMessageType = '',
    ) -> None:
        """ SQL table containt.

            The definition is the SQL that will be used to add the constraint.
            If the constraint is violated, we will show the message to the user
            or an empty string to get a default message.

            Examples of constraint definitions:
            - CHECK (x > 0)
            - FOREIGN KEY (abc) REFERENCES some_table(id)
            - UNIQUE (user_id)
        """
        super().__init__()
        self._definition = definition
        if message:
            self.message = message

    def get_definition(self, registry: Registry):
        return self._definition

    def apply_to_database(self, model: BaseModel):
        cr = model.env.cr
        conname = self.full_name(model)
        definition = self.get_definition(model.pool)
        current_definition = sql.constraint_definition(cr, model._table, conname)
        if current_definition == definition:
            return

        if current_definition:
            # constraint exists but its definition may have changed
            sql.drop_constraint(cr, model._table, conname)

        model.pool.post_constraint(
            cr, lambda cr: sql.add_constraint(cr, model._table, conname, definition), conname)
