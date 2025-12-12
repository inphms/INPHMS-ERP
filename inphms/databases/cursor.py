from __future__ import annotations
import typing as t
import psycopg2
import logging
import os
import threading
import time

from inspect import currentframe
from psycopg2.extensions import ISOLATION_LEVEL_REPEATABLE_READ
from psycopg2.sql import Composable
from contextlib import contextmanager
from datetime import datetime, timedelta

from .sql import SQL
from .utils import categorize_query, sql_counter
from .savepoint import Savepoint, _FlushingSavepoint
from .connection import ConnectionPool, PsycoConnection
from inphms.config import config
from inphms.tools import frame_codeinfo, Callbacks

if t.TYPE_CHECKING:
    from inphms.modules import Transaction

    _CursorProtocol = psycopg2.extensions.cursor
else:
    _CursorProtocol = object

_logger = logging.getLogger("inphms.db")

# _CursorProtocol declares the available methods and type information,
# at runtime, it is just an `object`


class BaseCursor(_CursorProtocol):
    """ Base class for cursors that manage pre/post commit hooks. """
    IN_MAX = 1000   # decent limit on size of IN queries - guideline = Oracle limit

    transaction: Transaction | None
    cache: dict[t.Any, t.Any]
    dbname: str

    def __init__(self) -> None:
        self.precommit = Callbacks()
        self.postcommit = Callbacks()
        self.prerollback = Callbacks()
        self.postrollback = Callbacks()
        self._now: datetime | None = None
        self.cache = {}
        # By default a cursor has no transaction object.  A transaction object
        # for managing environments is instantiated by registry.cursor().  It
        # is not done here in order to avoid cyclic module dependencies.
        self.transaction = None

    def flush(self) -> None:
        """ Flush the current transaction, and run precommit hooks. """
        if self.transaction is not None:
            self.transaction.flush()
        self.precommit.run()

    def clear(self) -> None:
        """ Clear the current transaction, and clear precommit hooks. """
        if self.transaction is not None:
            self.transaction.clear()
        self.precommit.clear()

    def reset(self) -> None:
        """ Reset the current transaction (this invalidates more that clear()).
            This method should be called only right after commit() or rollback().
        """
        if self.transaction is not None:
            self.transaction.reset()

    def execute(self, query, params=None, log_exceptions: bool = True) -> None:
        """ Execute a query inside the current transaction.
        """
        raise NotImplementedError

    def commit(self) -> None:
        """ Commit the current transaction.
        """
        raise NotImplementedError

    def rollback(self) -> None:
        """ Rollback the current transaction.
        """
        raise NotImplementedError

    def savepoint(self, flush: bool = True) -> Savepoint:
        """ context manager entering in a new savepoint

            With ``flush`` (the default), will automatically run (or clear) the
            relevant hooks.
        """
        if flush:
            return _FlushingSavepoint(self)
        else:
            return Savepoint(self)

    def __enter__(self):
        """ Using the cursor as a contextmanager automatically commits and
            closes it::

                with cr:
                    cr.execute(...)

                # cr is committed if no failure occurred
                # cr is closed in any case
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.commit()
        finally:
            self.close()

    def dictfetchone(self) -> dict[str, t.Any] | None:
        """ Return the first row as a dict (column_name -> value) or None if no rows are available. """
        raise NotImplementedError

    def dictfetchmany(self, size: int) -> list[dict[str, t.Any]]:
        res: list[dict[str, t.Any]] = []
        while size > 0 and (row := self.dictfetchone()) is not None:
            res.append(row)
            size -= 1
        return res

    def dictfetchall(self) -> list[dict[str, t.Any]]:
        """ Return all rows as dicts (column_name -> value). """
        res: list[dict[str, t.Any]] = []
        while (row := self.dictfetchone()) is not None:
            res.append(row)
        return res

    def now(self) -> datetime:
        """ Return the transaction's timestamp ``NOW() AT TIME ZONE 'UTC'``. """
        if self._now is None:
            self.execute("SELECT (now() AT TIME ZONE 'UTC')")
            row = self.fetchone()
            assert row
            self._now = row[0]
        return self._now


class Cursor(BaseCursor):
    """Represents an open transaction to the PostgreSQL DB backend,
       acting as a lightweight wrapper around psycopg2's
       ``cursor`` objects.
    """
    sql_from_log: dict[str, tuple[int, float]]
    sql_into_log: dict[str, tuple[int, float]]
    sql_log_count: int

    def __init__(self, pool: ConnectionPool, dbname: str, dsn: dict):
        super().__init__()
        self.sql_from_log = {}
        self.sql_into_log = {}

        # default log level determined at cursor creation, could be
        # overridden later for debugging purposes
        self.sql_log_count = 0

        # avoid the call of close() (by __del__) if an exception
        # is raised by any of the following initializations
        self._closed: bool = True

        self.__pool: ConnectionPool = pool
        self.dbname = dbname

        self._cnx: PsycoConnection = pool.borrow(dsn)
        self._obj: psycopg2.extensions.cursor = self._cnx.cursor()
        if _logger.isEnabledFor(logging.DEBUG):
            self.__caller = frame_codeinfo(currentframe(), 2)
        else:
            self.__caller = False
        self._closed = False   # real initialization value
        # See the docstring of this class.
        self.connection.set_isolation_level(ISOLATION_LEVEL_REPEATABLE_READ)
        self.connection.set_session(readonly=pool.readonly)

        if os.getenv('INPHMS_FAKETIME_TEST_MODE') and self.dbname in config['db_list']:
            self.execute("SET search_path = public, pg_catalog;")
            self.commit()  # ensure that the search_path remains after a rollback

    def __build_dict(self, row: tuple) -> dict[str, t.Any]:
        description = self._obj.description
        assert description, "Query does not have results"
        return {column.name: row[index] for index, column in enumerate(description)}

    def dictfetchone(self) -> dict[str, t.Any] | None:
        row = self._obj.fetchone()
        return self.__build_dict(row) if row else None

    def dictfetchmany(self, size) -> list[dict[str, t.Any]]:
        return [self.__build_dict(row) for row in self._obj.fetchmany(size)]

    def dictfetchall(self) -> list[dict[str, t.Any]]:
        return [self.__build_dict(row) for row in self._obj.fetchall()]

    def __del__(self):
        if not self._closed and not self._cnx.closed:
            # Oops. 'self' has not been closed explicitly.
            # The cursor will be deleted by the garbage collector,
            # but the database connection is not put back into the connection
            # pool, preventing some operation on the database like dropping it.
            # This can also lead to a server overload.
            msg = "Cursor not closed explicitly\n"
            if self.__caller:
                msg += "Cursor was created at %s:%s" % self.__caller
            else:
                msg += "Please enable sql debugging to trace the caller."
            _logger.warning(msg)
            self._close(True)

    def _format(self, query, params=None) -> str:
        encoding = psycopg2.extensions.encodings[self.connection.encoding]
        return self.mogrify(query, params).decode(encoding, 'replace')

    def mogrify(self, query, params=None) -> bytes:
        if isinstance(query, SQL):
            assert params is None, "Unexpected parameters for SQL query object"
            query, params = query.code, query.params
        return self._obj.mogrify(query, params)

    def execute(self, query, params=None, log_exceptions: bool = True) -> None:
        global sql_counter

        if isinstance(query, SQL):
            assert params is None, "Unexpected parameters for SQL query object"
            query, params = query.code, query.params

        if params and not isinstance(params, (tuple, list, dict)):
            # psycopg2's TypeError is not clear if you mess up the params
            raise ValueError("SQL query parameters should be a tuple, list or dict; got %r" % (params,))

        start = time.time()
        try:
            self._obj.execute(query, params)
        except Exception as e:
            if log_exceptions:
                _logger.error("bad query: %s\nERROR: %s", self._obj.query or query, e)
            raise
        finally:
            delay = time.time() - start
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug("[%.3f ms] query: %s", 1000 * delay, self._format(query, params))

        # simple query count is always computed
        self.sql_log_count += 1
        sql_counter += 1

        current_thread = threading.current_thread()
        if hasattr(current_thread, 'query_count'):
            current_thread.query_count += 1
        if hasattr(current_thread, 'query_time'):
            current_thread.query_time += delay

        # optional hooks for performance and tracing analysis
        for hook in getattr(current_thread, 'query_hooks', ()):
            hook(self, query, params, start, delay)

        # advanced stats
        if _logger.isEnabledFor(logging.DEBUG):
            if obj_query := self._obj.query:
                query = obj_query.decode()
            query_type, table = categorize_query(query)
            log_target = None
            if query_type == 'into':
                log_target = self.sql_into_log
            elif query_type == 'from':
                log_target = self.sql_from_log
            if log_target:
                stat_count, stat_time = log_target.get(table or '', (0, 0))
                log_target[table or ''] = (stat_count + 1, stat_time + delay * 1E6)
        return None

    def execute_values(self, query, argslist, template=None, page_size=100, fetch=False):
        """ A proxy for psycopg2.extras.execute_values which can log all queries like execute.
            But this method cannot set log_exceptions=False like execute
        """
        # Inphms Cursor only proxies all methods of psycopg2 Cursor. This is a patch for problems caused by passing
        # self instead of self._obj to the first parameter of psycopg2.extras.execute_values.
        if isinstance(query, Composable):
            query = query.as_string(self._obj)
        return psycopg2.extras.execute_values(self, query, argslist, template=template, page_size=page_size, fetch=fetch)

    def print_log(self) -> None:
        global sql_counter

        if not _logger.isEnabledFor(logging.DEBUG):
            return

        def process(log_type: str):
            sqllogs = {'from': self.sql_from_log, 'into': self.sql_into_log}
            sqllog = sqllogs[log_type]
            total = 0.0
            if sqllog:
                _logger.debug("SQL LOG %s:", log_type)
                for table, (stat_count, stat_time) in sorted(sqllog.items(), key=lambda k: k[1]):
                    delay = timedelta(microseconds=stat_time)
                    _logger.debug("table: %s: %s/%s", table, delay, stat_count)
                    total += stat_time
                sqllog.clear()
            total_delay = timedelta(microseconds=total)
            _logger.debug("SUM %s:%s/%d [%d]", log_type, total_delay, self.sql_log_count, sql_counter)

        process('from')
        process('into')
        self.sql_log_count = 0

    @contextmanager
    def _enable_logging(self):
        """ Forcefully enables logging for this cursor, restores it afterwards.

            Updates the logger in-place, so not thread-safe.
        """
        level = _logger.level
        _logger.setLevel(logging.DEBUG)
        try:
            yield
        finally:
            _logger.setLevel(level)

    def close(self) -> None:
        if not self.closed:
            return self._close(False)

    def _close(self, leak: bool = False) -> None:
        if not self._obj:
            return

        self.cache.clear()

        # advanced stats only at logging.DEBUG level
        self.print_log()

        self._obj.close()

        # This force the cursor to be freed, and thus, available again. It is
        # important because otherwise we can overload the server very easily
        # because of a cursor shortage (because cursors are not garbage
        # collected as fast as they should). The problem is probably due in
        # part because browse records keep a reference to the cursor.
        del self._obj

        # Clean the underlying connection, and run rollback hooks.
        self.rollback()

        self._closed = True

        if leak:
            self._cnx.leaked = True  # type: ignore
        else:
            chosen_template = config['db_template']
            keep_in_pool = self.dbname not in ('template0', 'template1', 'postgres', chosen_template)
            self.__pool.give_back(self._cnx, keep_in_pool=keep_in_pool)

    def commit(self) -> None:
        """ Perform an SQL `COMMIT` """
        self.flush()
        self._cnx.commit()
        self.clear()
        self._now = None
        self.prerollback.clear()
        self.postrollback.clear()
        self.postcommit.run()

    def rollback(self) -> None:
        """ Perform an SQL `ROLLBACK` """
        self.clear()
        self.postcommit.clear()
        self.prerollback.run()
        self._cnx.rollback()
        self._now = None
        self.postrollback.run()

    def __getattr__(self, name):
        if self._closed and name == '_obj':
            raise psycopg2.InterfaceError("Cursor already closed")
        return getattr(self._obj, name)

    @property
    def closed(self) -> bool:
        return self._closed or bool(self._cnx.closed)

    @property
    def readonly(self) -> bool:
        return bool(self._cnx.readonly)

