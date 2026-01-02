from __future__ import annotations
import errno
from io import BytesIO
import logging
import os
import signal
import sys
import time
import psutil
import platform
import socket
import threading
import typing as t
import contextlib
import select

import werkzeug
from werkzeug.urls import uri_to_iri

from .utils import cron_database_list, preload_registries
from inphms import config
from inphms.tools import OrderedSet, dumpstacks
from inphms.tools.orm import log_ormcache_stats
from inphms.databases import db_connect, close_all
from inphms.modules.registry import Registry
from inphms.server.utils import SLEEP_INTERVAL, memory_info, thread_local, server_phoenix, \
    set_limit_memory_hard

if os.name != 'posix':
    setattr(signal, 'SIGHUP', -1)

if t.TYPE_CHECKING:
    from collections.abc import Callable

    _RetAddress : t.TypeAlias = t.Any
    _RequestType : t.TypeAlias = socket.socket | tuple[bytes, socket.socket]

_logger = logging.getLogger(__name__)


class CommonServer(object):
    _on_stop_funcs: list[Callable] = []

    def __init__(self, app) -> None:
        self.app = app
        self.interface = config['http_host'] or '0.0.0.0'
        self.port = config['http_port']

        self.pid = os.getpid()

    def close_socket(self, sock):
        """ Close a socket.
        """
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except socket.error as err:
            if err.errno == errno.EBADF:
                # Werkzeug > 0.9.6 closes the socket itself (see commit
                # https://github.com/mitsuhiko/werkzeug/commit/4d8ca089)
                return
            # On OSX, socket shutdowns both sides if any side closes it
            # causing an error 57 'Socket is not connected' on shutdown
            # of the other side (or something), see
            # http://bugs.python.org/issue4397
            # note: stdlib fixed test, not behavior
            if err.errno != errno.ENOTCONN or platform.system() not in ['Darwin', 'Windows']:
                raise
        sock.close()
    
    @classmethod
    def on_stop(cls, func):
        cls._on_stop_funcs.append(func)
    
    def stop(self):
        for func in self._on_stop_funcs:
            try:
                _logger.debug("On stop: %s", func)
                func()
            except Exception:
                _logger.exception(f"Error during shutdown in {func.__name__}", exc_info=True)


class ThreadedServer(CommonServer):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.main_thread_id = threading.current_thread().ident

        self.quit_signal_count = 0

        self.httpd = None
        self.limit_reached_threads : set = set()
        self.limit_reached_time = None

    def run(self, preload=None, stop=False):
        with Registry._lock:
            self.start(stop=stop)
            rc = preload_registries(preload)

        if stop:
            if config['test_enable']:
                from inphms.tests.result import _logger as logger  # noqa: PLC0415
                with Registry.registries._lock:
                    for db, registry in Registry.registries.items():
                        report = registry._assertion_report
                        log = logger.error if not report.wasSuccessful() \
                         else logger.warning if not report.testsRun \
                         else logger.info
                        log("%s when loading database %r", report, db)
            self.stop()
            return rc
        
        self.cron_spawn()

        try:
            while self.quit_signal_count == 0:
                self.process_limit()
                if self.limit_reached_time:
                    def has_other_valid_request() -> bool:
                        return any(not t.daemon and t not in self.limit_reached_threads for t in threading.enumerate() if getattr(t, 'type', None) == 'http')
                    if (not has_other_valid_request() or (time.time() - self.limit_reached_time) > SLEEP_INTERVAL):
                        _logger.info("Dumping stacktrace of limit exceeding threads before reloading...")
                        dumpstacks(thread_idents=[thread.ident for thread in self.limit_reached_threads])
                        self.reload()
                    else:
                        time.sleep(1)
                else:
                    time.sleep(SLEEP_INTERVAL)
        except KeyboardInterrupt:
            pass
    
        self.stop()

    ####################
    # Limit processing #
    ####################
    def process_limit(self):
        memory = memory_info(psutil.Process(os.getpid()))
        if config['limit_memory_soft'] and memory > config['limit_memory_soft']:
            _logger.warning("Memory limit reached: %s", memory)
            self.limit_reached_threads.add(threading.current_thread())
        
        for thread in threading.enumerate():
            thread_type = getattr(thread, 'type', None)
            if not thread.daemon and thread_type != 'websocket' or thread_type == 'cron':
                # apply limits on cron threads and HTTP threads
                if getattr(thread, 'start_time', None):
                    thread_exc_time = time.time() - thread.start_time
                    thread_time_limit = config['limit_time_http']
                    if (getattr(thread, 'type', None) == 'cron' and config['limit_time_cron'] and config['limit_time_cron'] > 0):
                        thread_time_limit = config['limit_time_cron']
                    if thread_time_limit and thread_exc_time > thread_time_limit:
                        _logger.warning("Thread %s time limit reached: %s", thread.ident, thread_exc_time)
                        self.limit_reached_threads.add(thread)
        
        # Clean-up threads that are no longer alive
        # e.g. threads that exceeded their real time,
        # but which finished before the server could restart.
        for thread in list(self.limit_reached_threads):
            if not thread.is_alive():
                self.limit_reached_threads.remove(thread)
        if self.limit_reached_threads:
            self.limit_reached_time = self.limit_reached_time or time.time()
        else:
            self.limit_reached_time = None
        
    
    ####################
    # Cron processing  #
    ####################
    def cron_spawn(self):
        for i in range(config['max_cron_threads']):
            t = threading.Thread(target=self.cron_thread, args=(i,), name=f"inphms.service.cron.cron{i}")
            t.daemon = True
            t.type = 'cron'
            t.start()
            _logger.debug("cron%d started!", i)
    
    def cron_thread(self, number):
        
        from inphms.addons.base.models.ir_cron import IrCron  # noqa: PLC0415

        def _run_cron(cr):
            pg_conn = cr._cnx
            # LISTEN / NOTIFY doesn't work in recovery mode
            cr.execute("SELECT pg_is_in_recovery()")
            in_recovery = cr.fetchone()[0]
            if not in_recovery:
                cr.execute("LISTEN cron_trigger")
            else:
                _logger.warning("PG cluster in recovery mode, cron trigger not activated")
            cr.commit()
            check_all_time = 0.0  # last time that we listed databases, initialized far in the past
            all_db_names = []
            alive_time = time.monotonic()
            while config['limit_time_worker_cron'] <= 0 or (time.monotonic() - alive_time) <= config['limit_time_worker_cron']:
                select.select([pg_conn], [], [], SLEEP_INTERVAL + number)
                time.sleep(number / 100)
                try:
                    pg_conn.poll()
                except Exception:
                    if pg_conn.closed:
                        # connection closed, just exit the loop
                        return
                    raise
                notified = OrderedSet(
                    notif.payload
                    for notif in pg_conn.notifies
                    if notif.channel == 'cron_trigger'
                )
                pg_conn.notifies.clear()  # free resources

                if time.time() - SLEEP_INTERVAL > check_all_time:
                    # check all databases
                    # last time we checked them was `now - SLEEP_INTERVAL`
                    check_all_time = time.time()
                    # process notified databases first, then the other ones
                    all_db_names = OrderedSet(cron_database_list())
                    db_names = [
                        *(db for db in notified if db in all_db_names),
                        *(db for db in all_db_names if db not in notified),
                    ]
                else:
                    # restrict to notified databases only
                    db_names = notified.intersection(all_db_names)
                    if not db_names:
                        continue

                _logger.debug('cron%d polling for jobs (notified: %s)', number, notified)
                for db_name in db_names:
                    thread = threading.current_thread()
                    thread.start_time = time.time()
                    try:
                        IrCron._process_jobs(db_name)
                    except Exception:
                        _logger.warning('cron%d encountered an Exception:', number, exc_info=True)
                    thread.start_time = None

        while True:
            conn = db_connect('postgres')
            with contextlib.closing(conn.cursor()) as cr:
                _run_cron(cr)
                cr._cnx.close()
            _logger.info('cron%d max age (%ss) reached, releasing connection.', number, config['limit_time_worker_cron'])

    ####################
    # HTTP processing  #
    ####################
    def http_spawn(self):
        self.httpd = ThreadedWSGIServerReloadable(self.interface, self.port, self.app)
        threading.Thread(target=self.httpd.serve_forever,
                         name="inphms.server.httpd",
                         daemon=True,).start()

    ######################
    # Engine processing  #
    ######################
    def reload(self):
        # from .serving import restart
        # restart()
        os.kill(self.pid, signal.SIGHUP)
    
    def start(self, stop=False):
        _logger.debug("Setting up HTTP server...")
        set_limit_memory_hard()
        if os.name == 'posix':
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGCHLD, self.signal_handler)
            signal.signal(signal.SIGHUP, self.signal_handler)
            signal.signal(signal.SIGXCPU, self.signal_handler)
            signal.signal(signal.SIGQUIT, dumpstacks)
            signal.signal(signal.SIGUSR1, log_ormcache_stats)
            signal.signal(signal.SIGUSR2, log_ormcache_stats)
        elif os.name == 'nt':
            import win32api
            win32api.SetConsoleCtrlHandler(lambda sig: self.signal_handler(sig, None), 1)
        
        if config['test_enable'] or (config['http_enable'] and not stop):
            self.http_spawn()

    def stop(self):
        if server_phoenix:
            _logger.info("Initiating restart...")
        else:
            _logger.info("Initiating shutdown...")
            _logger.info("Hit CTRL+C again for a quick shutdown.")
        
        stop_time = time.time()
        if self.httpd:
            self.httpd.shutdown()
        super().stop()

        # Manually join() all threads before calling sys.exit() to allow a second signal
        # to trigger _force_quit() in case some non-daemon threads won't exit cleanly.
        # threading.Thread.join() should not mask signals (at least in python 2.5).
        me = threading.current_thread()
        _logger.debug('current thread: %r', me)
        for thread in threading.enumerate():
            _logger.debug('process %r (%r)', thread, thread.daemon)
            if (thread != me and not thread.daemon and thread.ident != self.main_thread_id and
                    thread not in self.limit_reached_threads):
                while thread.is_alive() and (time.time() - stop_time) < 1:
                    # We wait for requests to finish, up to 1 second.
                    _logger.debug('join and sleep')
                    # Need a busyloop here as thread.join() masks signals
                    # and would prevent the forced shutdown.
                    thread.join(0.05)
                    time.sleep(0.05)
        
        close_all()

        current_process = psutil.Process()
        children = current_process.children(recursive=False)
        for child in children:
            _logger.info('A child process was found, pid is %s, process may hang', child)

        _logger.debug("-" * 10)
        logging.shutdown()


    def signal_handler(self, sig, frame):
        if sig in [signal.SIGINT, signal.SIGTERM]:
            # -INTERUPT OR -TERIMINATE
            print("sig is in term or int")
            self.quit_signal_count += 1
            if self.quit_signal_count > 1:
                # logging already is shutdown probably
                sys.stderr.write("Forced shutdown\n")
                os._exit(0)
            raise KeyboardInterrupt()
        elif hasattr(signal, 'SIGXCPU') and sig == signal.SIGXCPU:
            sys.stderr.write("CPU time limit exceeded! Shutting down immediately\n")
            sys.stderr.flush()
            os._exit(0)
        elif sig == signal.SIGHUP:
            # restart on kill -HUP
            global server_phoenix
            server_phoenix = True
            self.quit_signal_count += 1
            raise KeyboardInterrupt()


###############
# WSGI SERVER #
###############
class LoggingBaseMixin(object):
    def handle_error(self, request, client_address):
        t, e, _ = sys.exc_info()
        if t == socket.error and e.errno == errno.EPIPE:
            # broken pipe, ignore error
            return
        _logger.exception('Exception happened during processing of request from %s', client_address)

class ThreadedWSGIServerReloadable(LoggingBaseMixin, werkzeug.serving.ThreadedWSGIServer):
    def __init__(self, host, port, app) -> None:
        super().__init__(host, port, app, handler=RequestHandler)
        self.daemon_threads = False

    def server_bind(self):
        self.reload_socket = False
        super().server_bind()
        _logger.info("HTTP Server (werkzeug) running on %s:%s", self.server_name, self.server_port)

    def process_request(self, request: _RequestType, client_address: _RetAddress) -> None:
        t = threading.Thread(target=self.process_request_thread,
                             args=(request, client_address))
        t.daemon = self.daemon_threads
        setattr(t, 'type', 'http')
        setattr(t, 'start_time', time.time())
        t.start()


###################
# REQUEST HANDLER #
###################
class BaseRequestHandler(werkzeug.serving.WSGIRequestHandler):
    def log_request(self, code: t.Union[int, str] = "-", size: t.Union[int, str] = "-") -> None:
        try:
            path = uri_to_iri(self.path)
            fragment = thread_local.rpc_model_method
            if fragment:
                path += '#' + fragment
            msg = f"{self.command} {path} {self.request_version}"
        except AttributeError:
            msg = self.requestline

        code = str(code)

        if code[0] == "1":  # 1xx - Informational
            msg = werkzeug.serving._ansi_style(msg, "bold")
        elif code == "200":  # 2xx - Success
            pass
        elif code == "304":  # 304 - Resource Not Modified
            msg = werkzeug.serving._ansi_style(msg, "cyan")
        elif code[0] == "3":  # 3xx - Redirection
            msg = werkzeug.serving._ansi_style(msg, "green")
        elif code == "404":  # 404 - Resource Not Found
            msg = werkzeug.serving._ansi_style(msg, "yellow")
        elif code[0] == "4":  # 4xx - Client Error
            msg = werkzeug.serving._ansi_style(msg, "bold", "red")
        else:  # 5xx, or any other response
            msg = werkzeug.serving._ansi_style(msg, "bold", "magenta")

        self.log("info", '"%s" %s %s', msg, code, size)

class RequestHandler(BaseRequestHandler):
    def setup(self):
        # timeout to avoid chrome headless preconnect during tests
        if config['test_enable']:
            self.timeout = 5
        super().setup()
        me = threading.current_thread()
        me.name = f"inphms.server.http.request.{(me.ident,)}"

    def make_environ(self):
        environ = super().make_environ()
        environ['socket'] = self.connection
        if self.headers.get('Upgrade') == 'websocket':
            self.protocol_version = "HTTP/1.1"
        return environ
    
    def send_header(self, keyword, value):
        if self.headers.get('Upgrade') == 'websocket' and keyword == 'Connection' and value == 'close':
            self.close_connection = True
            return
        super().send_header(keyword, value)
    
    def end_headers(self, *a, **kw):
        super().end_headers(*a, **kw)
        if self.headers.get('Upgrade') == 'websocket':
            self.rfile = BytesIO()
            self.wfile = BytesIO()
    
    def log_error(self, format, *args):
        if format == "Request timed out: %r" and config['test_enable']:
            _logger.info(format, *args)
        else:
            super().log_error(format, *args)
