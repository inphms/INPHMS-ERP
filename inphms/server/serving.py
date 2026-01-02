from __future__ import annotations
import logging
import os
from os.path import basename
import signal
import subprocess
import sys
import platform
import threading

from inphms import config
from inphms.release import NT_SERVICE_NAME
from inphms.server import root, ThreadedServer
from inphms.server.utils import strip_sys_argv, server_phoenix
from inphms.tools import osutils, gc

if os.name == 'posix':
    pass
else:
    signal.SIGHUP = -1

_logger = logging.getLogger(__name__)

server = None


def load_base_modules():
    from inphms.modules import load_inphms_module
    with gc.disabling_gc():
        for mod in config['server_wide_modules']:
            try:
                load_inphms_module(mod)
            except Exception:
                _logger.exception("Error loading module %s", mod, exc_info=True)
                raise


def start(preload=None, stop=False) -> int:
    global server

    load_base_modules()

    if config['workers']:
        pass
    else:
        if platform.system() == 'Linux' and sys.maxsize > 2**32 and 'MALLOC_ARENA_MAX' not in os.environ:
            try:
                import ctypes
                libc = ctypes.CDLL('libc.so.6')
                M_ARENA_MAX = -8
                assert libc.mallopt(ctypes.c_int(M_ARENA_MAX), ctypes.c_int(2))
            except Exception:
                _logger.warning("Could not set ARENA_MAX through mallopt()")
        server = ThreadedServer(root)

    watcher = None
    if 'reload' in config['dev_mode']:
        from .watcher import FSWatcherWatchdog
        watcher = FSWatcherWatchdog()
        watcher.start()
    
    rc = server.run(preload, stop)

    if watcher:
        watcher.stop()
    if server_phoenix:
        _restart()
    
    return rc if rc else 0

def restart():
    if os.name == 'nt':
        threading.Thread(target=_restart).start()
    else:
        os.kill(server.pid, signal.SIGHUP)

def _restart():
    if osutils.is_running_as_nt_service():
        subprocess.call("net stop {0} && net start {0}".format(NT_SERVICE_NAME), shell=True)
    exe = basename(sys.executable)
    args = strip_sys_argv()
    if not args or args[0] != exe:
        args.insert(0, exe)
    os.execve(sys.executable, args, os.environ)