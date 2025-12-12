from __future__ import annotations
import typing as t

from . import Index

if t.TYPE_CHECKING:
    from .utils import IndexDefinitionType, ConstraintMessageType


class UniqueIndex(Index):
    """ Unique index on the table.

        ``CREATE UNIQUE INDEX ... ON model_table <your definition>``.
    """
    unique = True

    def __init__(self, definition: IndexDefinitionType, message: ConstraintMessageType = ''):
        """ Unique index in SQL.

            The name of the SQL object will be "{model._table}_{key}". The definition
            is the SQL that will be used to create the constraint.
            You can also specify a message to be used when constraint is violated.

            Example of definition:
            - (group_id, active) WHERE active IS TRUE
            - USING btree (group_id, user_id)
        """
        super().__init__(definition)
        if message:
            self.message = message
