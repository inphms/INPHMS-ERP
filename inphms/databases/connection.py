from __future__ import annotations
import psycopg2
import time
import typing as t
import logging
import threading
import warnings

from psycopg2.pool import PoolError

from inphms.release import MIN_PG_VERSION
from inphms.tools import locked, reverse_enumerate

if t.TYPE_CHECKING:
    from .cursor import Cursor


_logger = logging.getLogger("inphms.db")
_logger_conn = _logger.getChild("conn")


MAX_IDLE_TIMEOUT = 60 * 10


class PsycoConnection(psycopg2.extensions.connection):
    _pool_in_use: bool = False
    _pool_last_used: float = 0

    def lobject(*args, **kwargs):
        pass

    if hasattr(psycopg2.extensions, 'ConnectionInfo'):
        @property
        def info(self):
            class PsycoConnectionInfo(psycopg2.extensions.ConnectionInfo):
                @property
                def password(self):
                    pass
            return PsycoConnectionInfo(self)


class ConnectionPool:
    """ The pool of connections to database(s)

        Keep a set of connections to pg databases open, and reuse them
        to open cursors for all transactions.

        The connections are *not* automatically closed. Only a close_db()
        can trigger that.
    """
    _connections: list[PsycoConnection]

    def __init__(self, maxconn: int = 64, readonly: bool = False):
        self._connections = []
        self._maxconn = max(maxconn, 1)
        self._readonly = readonly
        self._lock = threading.Lock()

    def __repr__(self):
        used = sum(1 for c in self._connections if c._pool_in_use)
        count = len(self._connections)
        mode = 'read-only' if self._readonly else 'read/write'
        return f"ConnectionPool({mode};used={used}/count={count}/max={self._maxconn})"

    @property
    def readonly(self) -> bool:
        return self._readonly

    def _debug(self, msg: str, *args):
        _logger_conn.debug(('%r ' + msg), self, *args)

    @locked
    def borrow(self, connection_info: dict) -> PsycoConnection:
        """ Borrow a PsycoConnection from the pool. If no connection is available, create a new one
            as long as there are still slots available. Perform some garbage-collection in the pool:
            idle, dead and leaked connections are removed.

            :param dict connection_info: dict of psql connection keywords
            :rtype: PsycoConnection
        """
        # free idle, dead and leaked connections
        for i, cnx in reverse_enumerate(self._connections):
            if not cnx._pool_in_use and not cnx.closed and time.time() - cnx._pool_last_used > MAX_IDLE_TIMEOUT:
                self._debug('Close connection at index %d: %r', i, cnx.dsn)
                cnx.close()
            if cnx.closed:
                self._connections.pop(i)
                self._debug('Removing closed connection at index %d: %r', i, cnx.dsn)
                continue
            if getattr(cnx, 'leaked', False):
                delattr(cnx, 'leaked')
                cnx._pool_in_use = False
                _logger.info('%r: Free leaked connection to %r', self, cnx.dsn)

        for i, cnx in enumerate(self._connections):
            if not cnx._pool_in_use and self._dsn_equals(cnx.dsn, connection_info):
                try:
                    cnx.reset()
                except psycopg2.OperationalError:
                    self._debug('Cannot reset connection at index %d: %r', i, cnx.dsn)
                    # psycopg2 2.4.4 and earlier do not allow closing a closed connection
                    if not cnx.closed:
                        cnx.close()
                    continue
                cnx._pool_in_use = True
                self._debug('Borrow existing connection to %r at index %d', cnx.dsn, i)

                return cnx

        if len(self._connections) >= self._maxconn:
            # try to remove the oldest connection not used
            for i, cnx in enumerate(self._connections):
                if not cnx._pool_in_use:
                    self._connections.pop(i)
                    if not cnx.closed:
                        cnx.close()
                    self._debug('Removing old connection at index %d: %r', i, cnx.dsn)
                    break
            else:
                # note: this code is called only if the for loop has completed (no break)
                raise PoolError('The Connection Pool Is Full')

        try:
            result = psycopg2.connect(
                connection_factory=PsycoConnection,
                **connection_info)
        except psycopg2.Error:
            _logger.info('Connection to the database failed')
            raise
        if result.server_version < MIN_PG_VERSION * 10000:
            warnings.warn(f"Postgres version is {result.server_version}, lower than minimum required {MIN_PG_VERSION * 10000}")
        result._pool_in_use = True
        self._connections.append(result)
        self._debug('Create new connection backend PID %d', result.get_backend_pid())

        return result

    @locked
    def give_back(self, connection: PsycoConnection, keep_in_pool: bool = True):
        self._debug('Give back connection to %r', connection.dsn)
        try:
            index = self._connections.index(connection)
        except ValueError:
            raise PoolError('This connection does not belong to the pool')

        if keep_in_pool:
            # Release the connection and record the last time used
            connection._pool_in_use = False
            connection._pool_last_used = time.time()
            self._debug('Put connection to %r in pool', connection.dsn)
        else:
            cnx = self._connections.pop(index)
            self._debug('Forgot connection to %r', cnx.dsn)
            cnx.close()

    @locked
    def close_all(self, dsn: dict | str | None = None):
        count = 0
        last = None
        for i, cnx in reverse_enumerate(self._connections):
            if dsn is None or self._dsn_equals(cnx.dsn, dsn):
                cnx.close()
                last = self._connections.pop(i)
                count += 1
        if count:
            _logger.info(
                '%r: Closed %d connections %s', self, count,
                (dsn and last and 'to %r' % last.dsn) or '')

    def _dsn_equals(self, dsn1: dict | str, dsn2: dict | str) -> bool:
        alias_keys = {'dbname': 'database'}
        ignore_keys = ['password']
        dsn1, dsn2 = ({
            alias_keys.get(key, key): str(value)
            for key, value in (psycopg2.extensions.parse_dsn(dsn) if isinstance(dsn, str) else dsn).items()
            if key not in ignore_keys
        } for dsn in (dsn1, dsn2))
        return dsn1 == dsn2


class Connection:
    """ A lightweight instance of a connection to postgres
    """
    def __init__(self, pool: ConnectionPool, dbname: str, dsn: dict):
        self.__dbname = dbname
        self.__dsn = dsn
        self.__pool = pool

    @property
    def dsn(self) -> dict:
        dsn = dict(self.__dsn)
        dsn.pop('password', None)
        return dsn

    @property
    def dbname(self) -> str:
        return self.__dbname

    def cursor(self) -> Cursor:
        from .cursor import Cursor
        _logger.debug('create cursor to %r', self.dsn)
        return Cursor(self.__pool, self.__dbname, self.__dsn)

    def __bool__(self):
        raise NotImplementedError()