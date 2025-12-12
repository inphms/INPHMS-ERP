# ruff: noqa

from .utils import db_connect, close_db, close_all, sql_counter, SQL_ORDER_BY_TYPE
from .connection import Connection
from .cursor import Cursor, BaseCursor
from .sql import SQL
from .query import Query


import psycopg2.extensions


def undecimalize(value, cr) -> float | None:
    if value is None:
        return None
    return float(value)


DECIMAL_TO_FLOAT_TYPE = psycopg2.extensions.new_type((1700,), 'float', undecimalize)
psycopg2.extensions.register_type(DECIMAL_TO_FLOAT_TYPE)
psycopg2.extensions.register_type(psycopg2.extensions.new_array_type((1231,), 'float[]', DECIMAL_TO_FLOAT_TYPE))


from .sqlutils import *
from .tablekinds import *