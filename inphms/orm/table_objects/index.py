from __future__ import annotations
import typing as t


from . import TableObject
from inphms.databases import sqlutils

if t.TYPE_CHECKING:
    from inphms.modules import Registry
    from ..models import BaseModel
    from .utils import IndexDefinitionType

    

class Index(TableObject):
    """ Index on the table.

        ``CREATE INDEX ... ON model_table <your definition>``.
    """
    unique: bool = False

    def __init__(self, definition: IndexDefinitionType):
        """ Index in SQL.

            The name of the SQL object will be "{model._table}_{key}". The definition
            is the SQL that will be used to create the constraint.

            Example of definition:
            - (group_id, active) WHERE active IS TRUE
            - USING btree (group_id, user_id)
        """
        super().__init__()
        self._index_definition = definition

    def get_definition(self, registry: Registry):
        if callable(self._index_definition):
            definition = self._index_definition(registry)
        else:
            definition = self._index_definition
        if not definition:
            return ''
        return f"{'UNIQUE ' if self.unique else ''}INDEX {definition}"

    def apply_to_database(self, model: BaseModel):
        cr = model.env.cr
        conname = self.full_name(model)
        definition = self.get_definition(model.pool)
        db_definition, db_comment = sqlutils.index_definition(cr, conname)
        if db_comment == definition or (not db_comment and db_definition):
            # keep when the definition matches the comment in the database
            # or if we have an index without a comment (this is used by support to tweak indexes)
            return

        if db_definition:
            # constraint exists but its definition may have changed
            sqlutils.drop_index(cr, conname, model._table)

        if callable(self._index_definition):
            definition_clause = self._index_definition(model.pool)
        else:
            definition_clause = self._index_definition
        if not definition_clause:
            # Don't create index with an empty definition
            return
        model.pool.post_constraint(cr, lambda cr: sqlutils.add_index(
            cr,
            conname,
            model._table,
            comment=definition,
            definition=definition_clause,
            unique=self.unique,
        ), conname)
