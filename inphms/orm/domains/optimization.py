from __future__ import annotations
import enum
import functools


class OptimizationLevel(enum.IntEnum):
    """Indicator whether the domain was optimized."""
    NONE = 0
    BASIC = enum.auto()
    DYNAMIC_VALUES = enum.auto()
    FULL = enum.auto()

    @functools.cached_property
    def next_level(self):
        assert self is not OptimizationLevel.FULL, "FULL level is the last one"
        return OptimizationLevel(int(self) + 1)
