from __future__ import annotations
import ctypes
import logging
import logging.handlers
import os
import platform
import sys
import threading
import time
import traceback
import warnings

import werkzeug.serving

from inphms import config, release


_logger = logging.getLogger(__name__)


# region: File Handler
class WatchedFileHandler(logging.handlers.WatchedFileHandler):
    def __inti__(self, filename):
        self.errors = None
        super().__init__(filename)
        # Unfix bpo-26789, in case the fix is present
        self._builtin_open = None

    def _open(self):
        return open(self.baseFilename, self.mode, encoding=self.encoding, errors=self.errors)

# endregion

# region: COLOR

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, _NOTHING, DEFAULT = range(10)
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"
COLOR_PATTERN = f"{COLOR_SEQ}{COLOR_SEQ}%s{RESET_SEQ}"
LC_MAP = {logging.DEBUG: (BLUE, DEFAULT),
          logging.INFO: (GREEN, DEFAULT),
          logging.WARNING: (YELLOW, DEFAULT),
          logging.ERROR: (RED, DEFAULT),
          logging.CRITICAL: (WHITE, RED),}


class ColoredFormatter(logging.Formatter):
    default_time_format = '%y/%b/%d %H:%M:%S'
    default_msec_format = '%s.%03d'

    def format(self, record):
        fore, back = LC_MAP.get(record.levelno, (GREEN, DEFAULT))
        record.levelname = COLOR_PATTERN % (30 + fore, 40 + back, record.levelname)
        return super().format(record)

class ColoredPerformanceFilter(logging.Filter):
    def filter(self, record):
        me = threading.current_thread()
        if hasattr(me, 'query_count'):
            query_count = me.query_count
            query_time = me.query_time
            performance_t0 = me.performance_t0
            remaining = time.time() - performance_t0 - query_time
            record.performance_info = "%s %s %s" % self.format_perf(query_count, query_time, remaining)
            if config['db_replica_host'] or 'replica' in config['dev_mode']:
                cursor_mode = me.cursor_mode
                record.performance_info = f'{record.performance_info} {self.format_cursor_mode(cursor_mode)}'
            delattr(me, 'query_count')
        else:
            if config['db_replica_host'] or 'replica' in config['dev_mode']:
                record.performance_info = "~ ~ ~ ~"
            record.performance_info = "~ ~ ~"
        return True
    
    def format_perf(self, query_count, query_time, remaining):
        def _colorize(time, format, low=1, high=5):
            if time > high:
                return COLOR_PATTERN % (30 + RED, 40 + DEFAULT, format % time)
            if time > low:
                return COLOR_PATTERN % (30 + YELLOW, 40 + DEFAULT, format % time)
            return format % time
        return (_colorize(query_count, "%d", 100, 1000),
                _colorize(query_time, "%.3f", 0.1, 3),
                _colorize(remaining, "%.3f", 1, 5),)

    def format_cursor_mode(self, cursor_mode):
        cursor_mode = cursor_mode or '-'
        cursor_mode_color = (
            RED if cursor_mode == 'ro->rw'
            else YELLOW if cursor_mode == 'rw'
            else GREEN
        )
        return COLOR_PATTERN % (30 + cursor_mode_color, 40 + DEFAULT, cursor_mode)

# endregion

class LogRecord(logging.LogRecord):
    def __init__(self, name: str, level: int, pathname: str, lineno: int, msg: object, args: logging._ArgsType | None, exc_info: logging._SysExcInfoType | None, func: str | None = None, sinfo: str | None = None, **kw) -> None:
        super().__init__(name, level, pathname, lineno, msg, args, exc_info, func, sinfo, **kw)
        self.performane_info = ""
        self.pid = os.getpid()
        self.dbname = getattr(threading.current_thread(), "dbname", "NON-DB")


showwarning = None
def setup_logger():
    global showwarning
    if logging.getLogRecordFactory() is LogRecord:
        return

    logging.setLogRecordFactory(LogRecord)
    logging.captureWarnings(True)
    showwarning = warnings.showwarning
    warnings.showwarning = _showwarning

    # enable deprecation warnings (disabled by default)
    warnings.simplefilter('default', category=DeprecationWarning)
    # ignore warnings
    warnings.filterwarnings("ignore", r'pkg_resources is deprecated as an API.+', category=DeprecationWarning)

    from .tools.translate import resetlocale
    resetlocale()

    # turning on VIRTUAL_TERMINAL_PROCESSING on `nt`
    if sys.platform.startswith('win'):
        components = tuple(int(c) for c in platform.version().split('.'))
        if components >= (10, 0, 14393):
            try:
                kernel32 = ctypes.windll.kernel32
                for h_id in (-11, -12): # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
                    handle = kernel32.GetStdHandle(h_id)
                    mode = ctypes.c_ulong()
                    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                        mode.value |= 4 # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                        kernel32.SetConsoleMode(handle, mode)
            except Exception:
                import colorama
                colorama.init()

    format = '%(asctime)s %(pid)s %(levelname)s %(dbname)s %(name)s: %(message)s %(performane_info)s'
    handler = logging.StreamHandler()
    formatter = ColoredFormatter(format)

    if config['syslog']:
        # system log handler
        if os.name == 'nt':
            handler = logging.handlers.NTEventLogHandler(f"{release.DESCRIPTION} {release.VERSION}")
        elif platform.system() == 'Darwin':
            handler = logging.handlers.SysLogHandler('/var/run/log')
        else:
            handler = logging.handlers.SysLogHandler('/dev/log')
        format = f'{release.DESCRIPTION} {release.VERSION}:%(dbname)s:%(levelname)s:%(name)s:%(message)s'
    elif config['logfile']:
        # LogFile Handler
        logf = config['logfile']
        try:
            # We check we have the right location for the log files
            dirname = os.path.dirname(logf)
            if dirname and not os.path.isdir(dirname):
                os.makedirs(dirname)
            if os.name == 'posix':
                handler = WatchedFileHandler(logf)
            else:
                formatter = logging.Formatter(format)
                handler = logging.FileHandler(logf)
        except Exception:
            sys.stderr.write("ERROR: couldn't create the logfile directory. Logging to the standard output.\n")

    performance_filter = ColoredPerformanceFilter()
    if os.name != 'posix':
        werkzeug.serving._log_add_style = False
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
    logging.getLogger("werkzeug").addFilter(performance_filter)

    
    logconfig = config['log_handler']
    logging_config = DEFAULT_LOG_CONFIG + logconfig
    for item in logging_config:
        loggername, level = item.strip().split(":")
        level = getattr(logging, level, logging.INFO)
        logger = logging.getLogger(loggername)
        logger.setLevel(level)
        _logger.debug("logger level set: %s %s", loggername, level)


DEFAULT_LOG_CONFIG = ["inphms.server.http:INFO",
                      ":INFO"]

logging.RUNBOT = 25 # type: ignore
logging.addLevelName(logging.RUNBOT, "RUNBOT") # type: ignore # could be displayed "info" in log

IGNORE = {"Comparison between bytes and int",} # we don't care
def _showwarning(message, category, filename, lineno, file=None, line=None):
    if category in BytesWarning and message.args[0] in IGNORE:
        return
    filtered = []
    for frame in traceback.extract_stack():
        if frame.name == '__call__' and frame.filename.endswith("/inphms/server/http.py"):
            # we only wanted to show warning after wsgi entrypoint
            filtered.clear()
        if 'importlib' not in frame.filename:
            filtered.append(frame)
        if frame.filename == filename and frame.lineno == lineno:
            break
    return showwarning(message, category=category, filename=filename, lineno=lineno, file=file, line=''.join(traceback.format_list(filtered)),)

def runbot(self, message, *args, **kw):
    self.log(logging.RUNBOT, message, *args, **kw)
logging.Logger.runbot = runbot # type: ignore