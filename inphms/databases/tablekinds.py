from __future__ import annotations
import enum

from .sql import SQL

__all__ = ["table_kind", "TableKind"]


class TableKind(enum.Enum):
    Regular = 'r'
    Temporary = 't'
    View = 'v'
    Materialized = 'm'
    Foreign = 'f'
    Other = None


def table_kind(cr, tablename: str) -> TableKind | None:
    """ Return the kind of a table, if ``tablename`` is a regular or foreign
        table, or a view (ignores indexes, sequences, toast tables, and partitioned
        tables; unlogged tables are considered regular)
    """
    cr.execute(SQL("""
        SELECT c.relkind, c.relpersistence
          FROM pg_class c
          JOIN pg_namespace n ON (n.oid = c.relnamespace)
         WHERE c.relname = %s
           AND n.nspname = current_schema
    """, tablename))
    if not cr.rowcount:
        return None

    kind, persistence = cr.fetchone()
    # special case: permanent, temporary, and unlogged tables differ by their
    # relpersistence, they're all "ordinary" (relkind = r)
    if kind == 'r':
        return TableKind.Temporary if persistence == 't' else TableKind.Regular

    try:
        return TableKind(kind)
    except ValueError:
        # NB: or raise? unclear if it makes sense to allow table_kind to
        #     "work" with something like an index or sequence
        return TableKind.Other
