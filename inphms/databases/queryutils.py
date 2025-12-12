from __future__ import annotations

from .sql import SQL
from .sqlutils import make_identifier

_SQL_JOINS = {
    "JOIN": SQL("JOIN"),
    "LEFT JOIN": SQL("LEFT JOIN"),
}


def _sql_from_table(alias: str, table: SQL) -> SQL:
    """ Return a FROM clause element from ``alias`` and ``table``. """
    if (alias_identifier := SQL.identifier(alias)) == table:
        return table
    return SQL("%s AS %s", table, alias_identifier)


def _sql_from_join(kind: SQL, alias: str, table: SQL, condition: SQL) -> SQL:
    """ Return a FROM clause element for a JOIN. """
    return SQL("%s %s ON (%s)", kind, _sql_from_table(alias, table), condition)


def _generate_table_alias(src_table_alias: str, link: str) -> str:
    """ Generate a standard table alias name. An alias is generated as following:

        - the base is the source table name (that can already be an alias)
        - then, the joined table is added in the alias using a 'link field name'
          that is used to render unique aliases for a given path
        - the name is shortcut if it goes beyond PostgreSQL's identifier limits

        .. code-block:: pycon

            >>> _generate_table_alias('res_users', link='parent_id')
            'res_users__parent_id'

        :param str src_table_alias: alias of the source table
        :param str link: field name
        :return str: alias
    """
    return make_identifier(f"{src_table_alias}__{link}")
