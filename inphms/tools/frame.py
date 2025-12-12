from __future__ import annotations
import logging
import traceback
import threading
import sys
import time

from inspect import getsourcefile
from contextlib import ContextDecorator

_logger = logging.getLogger(__name__)

__all__ = ["frame_codeinfo", "discardattr", "exception_to_unicode", "format_frame",
           "replace_exceptions", "dumpstacks"]


def frame_codeinfo(fframe, back=0):
    """ Return a (filename, line) pair for a previous frame .
        @return (filename, lineno) where lineno is either int or string==''
    """
    try:
        if not fframe:
            return "<unknown>", ''
        for _i in range(back):
            fframe = fframe.f_back
        try:
            fname = getsourcefile(fframe)
        except TypeError:
            fname = '<builtin>'
        lineno = fframe.f_lineno or ''
        return fname, lineno
    except Exception:
        return "<unknown>", ''


def format_frame(frame) -> str:
    code = frame.f_code
    return f'{code.co_name} {code.co_filename}:{frame.f_lineno}'


def discardattr(obj: object, key: str) -> None:
    """ Perform a ``delattr(obj, key)`` but without crashing if ``key`` is not present. """
    try:
        delattr(obj, key)
    except AttributeError:
        pass


def exception_to_unicode(e):
    if getattr(e, 'args', ()):
        return "\n".join(map(str, e.args))
    try:
        return str(e)
    except Exception:
        return "Unknown message"
    

class replace_exceptions(ContextDecorator):
    """
    Hide some exceptions behind another error. Can be used as a function
    decorator or as a context manager.

    .. code-block:

        @route('/super/secret/route', auth='public')
        @replace_exceptions(AccessError, by=NotFound())
        def super_secret_route(self):
            if not request.session.uid:
                raise AccessError("Route hidden to non logged-in users")
            ...

        def some_util():
            ...
            with replace_exceptions(ValueError, by=UserError("Invalid argument")):
                ...
            ...

    :param exceptions: the exception classes to catch and replace.
    :param by: the exception to raise instead.
    """
    def __init__(self, *exceptions, by):
        if not exceptions:
            raise ValueError("Missing exceptions")

        wrong_exc = next((exc for exc in exceptions if not issubclass(exc, Exception)), None)
        if wrong_exc:
            raise TypeError(f"{wrong_exc} is not an exception class.")

        self.exceptions = exceptions
        self.by = by

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None and issubclass(exc_type, self.exceptions):
            if isinstance(self.by, type) and exc_value.args:
                # copy the message
                raise self.by(exc_value.args[0]) from exc_value
            else:
                raise self.by from exc_value


def dumpstacks(sig=None, frame=None, thread_idents=None, log_level=logging.INFO):
    """ Signal handler: dump a stack trace for each existing thread or given
    thread(s) specified through the ``thread_idents`` sequence.
    """
    code = []

    def extract_stack(stack):
        for filename, lineno, name, line in traceback.extract_stack(stack):
            yield 'File: "%s", line %d, in %s' % (filename, lineno, name)
            if line:
                yield "  %s" % (line.strip(),)

    # code from http://stackoverflow.com/questions/132058/getting-stack-trace-from-a-running-python-application#answer-2569696
    # modified for python 2.5 compatibility
    threads_info = {th.ident: {'repr': repr(th),
                               'uid': getattr(th, 'uid', 'n/a'),
                               'dbname': getattr(th, 'dbname', 'n/a'),
                               'url': getattr(th, 'url', 'n/a'),
                               'query_count': getattr(th, 'query_count', 'n/a'),
                               'query_time': getattr(th, 'query_time', None),
                               'perf_t0': getattr(th, 'perf_t0', None)}
                    for th in threading.enumerate()}
    for threadId, stack in sys._current_frames().items():
        if not thread_idents or threadId in thread_idents:
            thread_info = threads_info.get(threadId, {})
            query_time = thread_info.get('query_time')
            perf_t0 = thread_info.get('perf_t0')
            remaining_time = None
            if query_time is not None and perf_t0:
                remaining_time = '%.3f' % (time.time() - perf_t0 - query_time)
                query_time = '%.3f' % query_time
            # qc:query_count qt:query_time pt:python_time (aka remaining time)
            code.append("\n# Thread: %s (db:%s) (uid:%s) (url:%s) (qc:%s qt:%s pt:%s)" %
                        (thread_info.get('repr', threadId),
                         thread_info.get('dbname', 'n/a'),
                         thread_info.get('uid', 'n/a'),
                         thread_info.get('url', 'n/a'),
                         thread_info.get('query_count', 'n/a'),
                         query_time or 'n/a',
                         remaining_time or 'n/a'))
            for line in extract_stack(stack):
                code.append(line)

    import inphms  # eventd
    if inphms.evented:
        # code from http://stackoverflow.com/questions/12510648/in-gevent-how-can-i-dump-stack-traces-of-all-running-greenlets
        import gc
        from greenlet import greenlet
        for ob in gc.get_objects():
            if not isinstance(ob, greenlet) or not ob:
                continue
            code.append("\n# Greenlet: %r" % (ob,))
            for line in extract_stack(ob.gr_frame):
                code.append(line)

    _logger.log(log_level, "\n".join(code))
