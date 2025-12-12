from __future__ import annotations
from collections import defaultdict


class Controller:
    children_classes: defaultdict = defaultdict(list)  # indexed by module

    @classmethod
    def __init_subclass__(cls):
        super().__init_subclass__()
        if Controller in cls.__bases__:
            path = cls.__module__.split('.')
            module = path[2] if path[:2] == ['inphms', 'addons'] else ''
            Controller.children_classes[module].append(cls)

    @property
    def env(self):
        from .utils import request
        return request.env if request else None
