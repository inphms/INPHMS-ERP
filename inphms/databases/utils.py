from __future__ import annotations
import typing as t
import re
import os

from werkzeug import urls
from collections import defaultdict

import inphms
from inphms.config import config
from .connection import ConnectionPool, Connection

if t.TYPE_CHECKING:
    from collections.abc import Mapping

_Pool: ConnectionPool | None = None
_Pool_readonly: ConnectionPool | None = None


def db_connect(to: str, allow_uri=False, readonly=False) -> Connection:
    global _Pool, _Pool_readonly  # noqa: PLW0603 (global-statement)

    maxconn = (config['db_maxconn_gevent'] if hasattr(inphms, 'evented') and inphms.evented else 0) or config['db_maxconn']
    _Pool_readonly if readonly else _Pool
    if readonly:
        if _Pool_readonly is None:
            _Pool_readonly = ConnectionPool(int(maxconn), readonly=True)
        pool = _Pool_readonly
    else:
        if _Pool is None:
            _Pool = ConnectionPool(int(maxconn), readonly=False)
        pool = _Pool

    db, info = connection_info_for(to, readonly)
    if not allow_uri and db != to:
        raise ValueError('URI connections not allowed')
    return Connection(pool, db, info)


def connection_info_for(db_or_uri: str, readonly=False) -> tuple[str, dict]:
    """ parse the given `db_or_uri` and return a 2-tuple (dbname, connection_params)

        Connection params are either a dictionary with a single key ``dsn``
        containing a connection URI, or a dictionary containing connection
        parameter keywords which psycopg2 can build a key/value connection string
        (dsn) from

        :param str db_or_uri: database name or postgres dsn
        :param bool readonly: used to load
            the default configuration from ``db_`` or ``db_replica_``.
        :rtype: (str, dict)
    """
    app_name = config['db_appname']
    # Using manual string interpolation for security reason and trimming at default NAMEDATALEN=63
    app_name = app_name.replace('{pid}', str(os.getpid()))[:63]
    if db_or_uri.startswith(('postgresql://', 'postgres://')):
        # extract db from uri
        us = urls.url_parse(db_or_uri)  # type: ignore
        if len(us.path) > 1:
            db_name = us.path[1:]
        elif us.username:
            db_name = us.username
        else:
            db_name = us.hostname # type: ignore
        return db_name, {'dsn': db_or_uri, 'application_name': app_name}

    connection_info = {'database': db_or_uri, 'application_name': app_name}
    for p in ('host', 'port', 'user', 'password', 'sslmode'):
        cfg = config['db_' + p]
        if readonly:
            cfg = config.get('db_replica_' + p, cfg)
        if cfg:
            connection_info[p] = cfg

    return db_or_uri, connection_info


def close_db(db_name: str) -> None:
    """ You might want to call inphms.modules.registry.Registry.delete(db_name) along this function."""
    if _Pool:
        _Pool.close_all(connection_info_for(db_name)[1])
    if _Pool_readonly:
        _Pool_readonly.close_all(connection_info_for(db_name)[1])


def close_all() -> None:
    if _Pool:
        _Pool.close_all()
    if _Pool_readonly:
        _Pool_readonly.close_all()


###################
# Query utilities #
###################
sql_counter: int = 0

re_from = re.compile(r'\bfrom\s+"?([a-zA-Z_0-9]+)\b', re.IGNORECASE)
re_into = re.compile(r'\binto\s+"?([a-zA-Z_0-9]+)\b', re.IGNORECASE)
IDENT_RE = re.compile(r'^[a-z0-9_][a-z0-9_$\-]*$', re.I)
SQL_ORDER_BY_TYPE = defaultdict(lambda: 16, {
    'int4': 1,          # 4 bytes aligned on 4 bytes
    'varchar': 2,       # variable aligned on 4 bytes
    'date': 3,          # 4 bytes aligned on 4 bytes
    'jsonb': 4,         # jsonb
    'text': 5,          # variable aligned on 4 bytes
    'numeric': 6,       # variable aligned on 4 bytes
    'bool': 7,          # 1 byte aligned on 1 byte
    'timestamp': 8,     # 8 bytes aligned on 8 bytes
    'float8': 9,        # 8 bytes aligned on 8 bytes
})

def categorize_query(decoded_query: str) -> tuple[t.Literal['from', 'into'], str] | tuple[t.Literal['other'], None]:
    res_into = re_into.search(decoded_query)
    # prioritize `insert` over `select` so `select` subqueries are not
    # considered when inside a `insert`
    if res_into:
        return 'into', res_into.group(1)

    res_from = re_from.search(decoded_query)
    if res_from:
        return 'from', res_from.group(1)

    return 'other', None


def named_to_positional_printf(string: str, args: Mapping) -> tuple[str, tuple]:
    """ Convert a named printf-style format string with its arguments to an
        equivalent positional format string with its arguments.
    """
    pargs = _PrintfArgs(args)
    return string.replace('%%', '%%%%') % pargs, tuple(pargs.values)


class _PrintfArgs:
    """ Helper object to turn a named printf-style format string into a positional one. """
    __slots__ = ('mapping', 'values')

    def __init__(self, mapping):
        self.mapping: Mapping = mapping
        self.values: list = []

    def __getitem__(self, key):
        self.values.append(self.mapping[key])
        return "%s"