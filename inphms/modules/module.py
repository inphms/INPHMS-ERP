from __future__ import annotations
import logging
import os
import sys

from inphms import config
import inphms.addons

_logger = logging.getLogger(__name__)

__all__ = ["setup_sys_path",
           "load_inphms_module", "current_test"]


current_test: bool = False
"""Indicates whteher we are in a test mode"""


def setup_sys_path() -> None:
    for p in (config.addons_base_dir, config.addons_global_dir):
        if os.access(p, os.R_OK) and p not in inphms.addons.__path__:
            inphms.addons.__path__.append(p)

    if not getattr(setup_sys_path, 'called', False):
        inphms.addons.__path__._path_finder = lambda *a: None
        setup_sys_path.called = True


def load_inphms_module(module: str) -> None:
    qualname = f"inphms.addons.{module}"
    if qualname in sys.modules:
        return
    try:
        __import__(qualname)
    except Exception:
        _logger.exception("Failed to load module %r", module)
        raise