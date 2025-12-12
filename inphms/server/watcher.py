from __future__ import annotations
import logging
import os
from os.path import basename


if os.name != 'posix':
    try:
        import watchdog
        from watchdog.observers import Observer
        from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent, FileSystemEventHandler
    except ImportError:
        watchdog = None # type: ignore


_logger = logging.getLogger(__name__)


class FSWatcher(object):
    def handle_file(self, path: str) -> bool:
        if path.endswith('.py') and not basename(path).startswith('.~'):
            try:
                source = open(path, 'rb').read() + b'\n'
                compile(source, path, 'exec')
            except IOError:
                _logger.error("AutoReload: Python code changed but cannot read file: %s", path, exc_info=True)
            except SyntaxError:
                _logger.error("AutoReload: Python code changed but invalid syntax in file: %s", path, exc_info=True)
            else:
                from inphms.server.serving import server_phoenix
                if not server_phoenix:
                    from .serving import restart
                    _logger.info("AutoReload: Python code changed, reloading server...")
                    restart()
                    return True
        return False

class FSWatcherWatchdog(FSWatcher, FileSystemEventHandler):
    def __init__(self) -> None:
        self.observer = Observer()
        import inphms.addons
        for path in inphms.addons.__path__:
            _logger.info("Watching %s for changes...", path)
            self.observer.schedule(self, path, recursive=True)
    
    def dispatch(self, event):
        if isinstance(event, (FileCreatedEvent, FileModifiedEvent, FileMovedEvent)):
            if not event.is_directory:
                path = getattr(event, 'dest_path', '') or event.src_path
                self.handle_file(path)
    
    def start(self) -> None:
        self.observer.start()
        _logger.info("AutoReload: Started watching for changes...")
    
    def stop(self) -> None:
        self.observer.stop()
        self.observer.join()
        