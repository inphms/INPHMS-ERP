from __future__ import annotations
import pkgutil
import os
import time
import importlib
import sys

from types import SimpleNamespace, ModuleType


class PatchImportHook:
    def __init__(self):
        self.hooks = set()
    
    def add_hook(self, name: str) -> None:
        self.hooks.add(name)
        if name in sys.modules:
            patch_module(name)
        
    def find_spec(self, name, path=None, target=None):
        if name not in self.hooks:
            return None # let python use another import hook to import this fullname
        
        # skip all finders before this one
        idx = sys.meta_path.index(self)
        for finder in sys.meta_path[idx + 1:]:
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                # we found a spec, change the loader
                def exec_module(module: ModuleType, exec_module=spec.loader.exec_module) -> None:
                    exec_module(module)
                    patch_module(module.__name__)
                
                spec.loader = SimpleNamespace(create_module=spec.loader.create_module, exec_module=exec_module)
                return spec
        raise ImportError(f"Couldn't load module to patch: {name}")


HOOK_IMPORT = PatchImportHook()
sys.meta_path.insert(0, HOOK_IMPORT)

def setup_patch() -> None:
    os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'):
        time.tzset()
    
    for submod in pkgutil.iter_modules(__path__):
        HOOK_IMPORT.add_hook(submod.name)


def patch_module(name: str) -> None:
    mod = importlib.import_module(f".{name}", __name__)
    mod.patch_module()