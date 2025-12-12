from __future__ import annotations
import re
import psycopg2.extensions
import functools

from operator import itemgetter

from ..utils import check_object_name, regex_read_group_spec
from inphms.databases import SQL

NO_ACCESS = '.'
LOG_ACCESS_COLUMNS = ['create_uid', 'create_date', 'write_uid', 'write_date']
MAGIC_COLUMNS = ['id'] + LOG_ACCESS_COLUMNS
INSERT_BATCH_SIZE = 100
UPDATE_BATCH_SIZE = 100
SQL_DEFAULT = psycopg2.extensions.AsIs("DEFAULT")

# valid SQL aggregation functions
READ_GROUP_AGGREGATE = {
    'sum': lambda table, expr: SQL('SUM(%s)', expr),
    'avg': lambda table, expr: SQL('AVG(%s)', expr),
    'max': lambda table, expr: SQL('MAX(%s)', expr),
    'min': lambda table, expr: SQL('MIN(%s)', expr),
    'bool_and': lambda table, expr: SQL('BOOL_AND(%s)', expr),
    'bool_or': lambda table, expr: SQL('BOOL_OR(%s)', expr),
    'array_agg': lambda table, expr: SQL('ARRAY_AGG(%s ORDER BY %s)', expr, SQL.identifier(table, 'id')),
    'array_agg_distinct': lambda table, expr: SQL('ARRAY_AGG(DISTINCT %s ORDER BY %s)', expr, expr),
    # 'recordset' aggregates will be post-processed to become recordsets
    'recordset': lambda table, expr: SQL('ARRAY_AGG(%s ORDER BY %s)', expr, SQL.identifier(table, 'id')),
    'count': lambda table, expr: SQL('COUNT(%s)', expr),
    'count_distinct': lambda table, expr: SQL('COUNT(DISTINCT %s)', expr),
}
READ_GROUP_DISPLAY_FORMAT = {
    # Careful with week/year formats:
    #  - yyyy (lower) must always be used, *except* for week+year formats
    #  - YYYY (upper) must always be used for week+year format
    #         e.g. 2006-01-01 is W52 2005 in some locales (de_DE),
    #                         and W1 2006 for others
    #
    # Mixing both formats, e.g. 'MMM YYYY' would yield wrong results,
    # such as 2006-01-01 being formatted as "January 2005" in some locales.
    # Cfr: http://babel.pocoo.org/en/latest/dates.html#date-fields
    'hour': 'hh:00 dd MMM',
    'day': 'dd MMM yyyy', # yyyy = normal year
    'week': "'W'w YYYY",  # w YYYY = ISO week-year
    'month': 'MMMM yyyy',
    'quarter': 'QQQ yyyy',
    'year': 'yyyy',
}


def parse_read_group_spec(spec: str) -> tuple:
    """ Return a triplet corresponding to the given field/property_name/aggregate specification. """
    res_match = regex_read_group_spec.match(spec)
    if not res_match:
        raise ValueError(
            f'Invalid aggregate/groupby specification {spec!r}.\n'
            '- Valid aggregate specification looks like "<field_name>:<agg>" example: "quantity:sum".\n'
            '- Valid groupby specification looks like "<no_datish_field_name>" or "<datish_field_name>:<granularity>" example: "date:month" or "<properties_field_name>.<property>:<granularity>".'
        )

    groups = res_match.groups()
    return groups[0], groups[2], groups[3]


def raise_on_invalid_object_name(name):
    if not check_object_name(name):
        msg = "The _name attribute %s is not valid." % name
        raise ValueError(msg)

from ..utils import parse_field_expr


class OriginIds:
    """ A reversible iterable returning the origin ids of a collection of ``ids``.
        Actual ids are returned as is, and ids without origin are not returned.
    """
    __slots__ = ['ids']

    def __init__(self, ids):
        self.ids = ids

    def __iter__(self):
        for id_ in self.ids:
            if id_ := id_ or getattr(id_, 'origin', None):
                yield id_

    def __reversed__(self):
        for id_ in reversed(self.ids):
            if id_ := id_ or getattr(id_, 'origin', None):
                yield id_


def fix_import_export_id_paths(fieldname):
    """ Fixes the id fields in import and exports, and splits field paths
        on '/'.

        :param str fieldname: name of the field to import/export
        :return: split field name
        :rtype: list of str
    """
    fixed_db_id = re.sub(r'([^/])\.id', r'\1/.id', fieldname)
    fixed_external_id = re.sub(r'([^/]):id', r'\1/id', fixed_db_id)
    return fixed_external_id.split('/')


def get_columns_from_sql_diagnostics(cr, diagnostics, *, check_registry=False) -> list[str]:
    """ Given the diagnostics of an error, return the affected column names by the constraint.
        Return an empty list if we cannot determine the columns.
    """
    if column := diagnostics.column_name:
        return [column]
    if not check_registry:
        return []
    cr.execute(SQL("""
        SELECT
            ARRAY(
                SELECT attname FROM pg_attribute
                WHERE attrelid = conrelid
                AND attnum = ANY(conkey)
            ) as "columns"
        FROM pg_constraint
        JOIN pg_class t ON t.oid = conrelid
        WHERE conname = %s
            AND t.relname = %s
    """, diagnostics.constraint_name, diagnostics.table_name))
    columns = cr.fetchone()
    return columns[0] if columns else []


def itemgetter_tuple(items):
    """ Fixes itemgetter inconsistency (useful in some cases) of not returning
        a tuple if len(items) == 1: always returns an n-tuple where n = len(items)
    """
    if len(items) == 0:
        return lambda a: ()
    if len(items) == 1:
        return lambda gettable: (gettable[items[0]],)
    return itemgetter(*items)


def to_record_ids(arg) -> list[int]:
    """ Return the record ids of ``arg``, which may be a recordset, an integer or a list of integers. """
    from .basemodel import BaseModel
    if isinstance(arg, BaseModel):
        return arg.ids
    elif isinstance(arg, int):
        return [arg] if arg else []
    else:
        return [id_ for id_ in arg if id_]


@functools.total_ordering
class ReversibleComparator:
    __slots__ = ('__item', '__none_first', '__reverse')

    def __init__(self, item, reverse: bool, none_first: bool):
        self.__item = item
        self.__reverse = reverse
        self.__none_first = none_first

    def __lt__(self, other: ReversibleComparator) -> bool:
        item = self.__item
        item_cmp = other.__item
        if item == item_cmp:
            return False
        if item is None:
            return self.__none_first
        if item_cmp is None:
            return not self.__none_first
        if self.__reverse:
            item, item_cmp = item_cmp, item
        return item < item_cmp

    def __eq__(self, other: ReversibleComparator) -> bool:
        return self.__item == other.__item

    def __hash__(self):
        return hash(self.__item)

    def __repr__(self):
        return f"<ReversibleComparator {self.__item!r}{' reverse' if self.__reverse else ''}>"


def check_company_domain_parent_of(self, companies):
    """ A `_check_company_domain` function that lets a record be used if either:
        - record.company_id = False (which implies that it is shared between all companies), or
        - record.company_id is a parent of any of the given companies.
    """
    if isinstance(companies, str):
        return ['|', ('company_id', '=', False), ('company_id', 'parent_of', companies)]

    companies = to_record_ids(companies)
    if not companies:
        return [('company_id', '=', False)]

    return [('company_id', 'in', [
        int(parent)
        for rec in self.env['res.company'].sudo().browse(companies)
        for parent in rec.parent_path.split('/')[:-1]
    ] + [False])]


def check_companies_domain_parent_of(self, companies):
    """ A `_check_company_domain` function that lets a record be used if
        any company in record.company_ids is a parent of any of the given companies.
    """
    if isinstance(companies, str):
        return [('company_ids', 'parent_of', companies)]

    companies = to_record_ids(companies)
    if not companies:
        return []

    return [('company_ids', 'in', [
        int(parent)
        for rec in self.env['res.company'].sudo().browse(companies)
        for parent in rec.parent_path.split('/')[:-1]
    ])]
