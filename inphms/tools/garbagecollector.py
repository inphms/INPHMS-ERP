""" Garage Collector Tools
"""

from __future__ import annotations
import contextlib
import gc
import logging
from time import thread_time_ns

_logger = logging.getLogger("gc")
_gc_start: int = 0
_gc_init_stats = gc.get_stats()
_gc_timings = [0, 0, 0]


def _to_ms(ns):
    return round(ns / 1_000_000, 2)


def _timing_gc_callback(event, info):
    global _gc_start
    gen = info['generation']
    if event == 'start':
        _gc_start = thread_time_ns()
        # python 3.14; gen2 is only collected when calling gc.collect() manually
        if gen == 2 and _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("info %s, starting collection of gen2", gc_info())
    else:
        timing = thread_time_ns() - _gc_start
        _gc_timings[gen] += timing
        _gc_start = 0
        if gen > 0:
            _logger.debug("collected %s in %.2fms", info, _to_ms(timing))


def gc_set_timing(*, enable: bool):
    """ Enable or disable timing callback.
    """
    if _timing_gc_callback in gc.callbacks:
        if enable:
            return
        gc.callbacks.remove(_timing_gc_callback)
    elif enable:
        global _gc_init_stats, _gc_timings
        _gc_init_stats = gc.get_stats()
        _gc_timings = [0, 0, 0]
        gc.callbacks.append(_timing_gc_callback)


def gc_info():
    """Return a dict with stats about the garbage collector."""
    stats = gc.get_stats()
    times = []
    cumulative_time = sum(_gc_timings) or 1
    for info, info_init, time in zip(stats, _gc_init_stats, _gc_timings):
        count = info['collections'] - info_init['collections']
        times.append({'avg_time': time // count if count > 0 else 0,
                      'time': _to_ms(time),
                      'pct': round(time / cumulative_time, 3)})
    return {'cumulative_time': _to_ms(cumulative_time),
            'time': times if _timing_gc_callback in gc.callbacks else (),
            'count': stats,
            'thresholds': (gc.get_count(), gc.get_threshold()), }


@contextlib.contextmanager
def disabling_gc():
    """Disable gc in the context manager."""
    if not gc.isenabled():
        yield False
        return
    gc.disable()
    _logger.debug('disabled, counts %s', gc.get_count())
    yield True
    counts = gc.get_count()
    gc.enable()
    _logger.debug('enabled, counts %s', counts)
