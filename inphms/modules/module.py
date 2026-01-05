from __future__ import annotations
import logging
import os
import sys
import traceback

from inphms import config
import inphms.addons
from .utils import TYPED_FIELD_DEFINITION_RE
import inphms.upgrade

_logger = logging.getLogger(__name__)

__all__ = ["setup_sys_path",
           "load_inphms_module", "current_test"]


current_test: bool = False
"""Indicates whteher we are in a test mode"""


def setup_sys_path() -> None:
    """
    Setup addons path, ``inphms.addons.__path__`` with various and explicit directories.
    """
    for p in (config.addons_base_dir, config.addons_global_dir):
        if os.access(p, os.R_OK) and p not in inphms.addons.__path__:
            inphms.addons.__path__.append(p)

    # hook upgrade path
    for up in config['upgrade_path']:
        if up not in inphms.upgrade.__path:
            inphms.upgrade.__path__.append(up)

    if not getattr(setup_sys_path, 'called', False):
        inphms.addons.__path__._path_finder = lambda *a: None
        inphms.upgrade.__path__._path_finder = lambda *a: None
        setup_sys_path.called = True


def load_inphms_module(module: str) -> None:
    qualname = f"inphms.addons.{module}"
    if qualname in sys.modules:
        return
    try:
        __import__(qualname)

        # Call the module's post-load hook. This can done before any model or
        # data has been initialized. This is ok as the post-load hook is for
        # server-wide (instead of registry-specific) functionalities.
        from inphms.modules import Manifest
        manifest = Manifest.for_addon(module)
        if post_load := manifest.get('post_load'):
            getattr(sys.modules[qualname], post_load)()

    except AttributeError as err:
        _logger.critical("Couldn't load module %s", module)
        trace = traceback.format_exc()
        match = TYPED_FIELD_DEFINITION_RE.search(trace)
        if match and "most likely due to a circular import" in trace:
            field_name = match['field_name']
            field_class = match['field_class']
            field_type = match['field_type'] or match['type_param']
            if "." not in field_type:
                field_type = f"{module}.{field_type}"
            raise AttributeError(
                f"{err}\n"
                "To avoid circular import for the the comodel use the annotation syntax:\n"
                f"    {field_name}: {field_type} = fields.{field_class}(...)\n"
                "and add at the beggining of the file:\n"
                "    from __future__ import annotations"
            ).with_traceback(err.__traceback__) from None
        raise
    except Exception:
        _logger.critical("Failed to load module %r", module)
        raise