from __future__ import annotations
import enum

__all__ = ["Sentinel", "SENTINEL"]


class Sentinel(enum.Enum):
    """Class for typing parameters with a sentinel as a default"""
    SENTINEL = -1


SENTINEL = Sentinel.SENTINEL
