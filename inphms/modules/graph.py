from __future__ import annotations
import typing as t
import logging
import functools

from inphms.tools import reset_cached_properties, OrderedSet
from inphms.databases import column_exists
from .manifest import Manifest

if t.TYPE_CHECKING:
    from inphms.databases import BaseCursor
    from collections.abc import Collection, Iterable, Iterator, Mapping
    from typing import Literal

    STATES = Literal["uninstallable",
                     "uninstalled",
                     "installed",
                     "to upgrade",
                     "to remove",
                     "to install",]

_logger = logging.getLogger(__name__)


class ModuleNode:
    """
    Loading and upgrade info for an Inphms module
    """
    def __init__(self, name: str, module_graph: ModuleGraph) -> None:
        # manifest data
        self.name: str = name
        # for performance reasons, use the cached value to avoid deepcopy; it is
        # acceptable in this context since we don't modify it
        manifest = Manifest.for_addon(name, display_warning=False)
        if manifest is not None:
            manifest.raw_value('')  # parse the manifest now
        self.manifest: Mapping = manifest or {}

        # ir_module_module data                     # column_name
        self.id: int = 0                            # id
        self.state: STATES = 'uninstalled'          # state
        self.demo: bool = False                     # demo
        self.installed_version: str | None = None   # latest_version (attention: Incorrect field names !! in ir_module.py)

        # info for upgrade
        self.load_state: STATES = 'uninstalled'     # the state when added to module_graph
        self.load_version: str | None = None        # the version when added to module_graph

        # dependency
        self.depends: OrderedSet[ModuleNode] = OrderedSet()
        self.module_graph: ModuleGraph = module_graph

    @functools.cached_property
    def order_name(self) -> str:
        if self.name.startswith('test_'):
            # The 'space' was chosen because it's smaller than any character that can be used by the module name.
            last_installed_dependency = max(self.depends, key=lambda m: (m.depth, m.order_name))
            return last_installed_dependency.order_name + ' ' + self.name

        return self.name

    @functools.cached_property
    def depth(self) -> int:
        """ Return the longest distance from self to module 'base' along dependencies. """
        if self.name.startswith('test_'):
            last_installed_dependency = max(self.depends, key=lambda m: (m.depth, m.order_name))
            return last_installed_dependency.depth

        return max(module.depth for module in self.depends) + 1 if self.depends else 0

    @functools.cached_property
    def phase(self) -> int:
        if self.name == 'base':
            return 0

        if self.module_graph.mode == 'load':
            return 1

        def not_in_the_same_phase(module: ModuleNode, dependency: ModuleNode) -> bool:
            return (module.state == 'to install') ^ (dependency.state == 'to install')

        return max(
            dependency.phase
            + (1 if not_in_the_same_phase(self, dependency) else 0)
            + (1 if dependency.name == 'base' else 0)
            for dependency in self.depends
        )

    @property
    def demo_installable(self) -> bool:
        return all(p.demo for p in self.depends)


class ModuleGraph:
    """
    Sorted Inphms modules ordered by (module.phase, module.depth, module.name)
    """

    def __init__(self, cr: BaseCursor, mode: Literal['load', 'update'] = 'load') -> None:
        # mode 'load': for simply loading modules without updating them
        # mode 'update': for loading and updating modules
        self.mode: Literal['load', 'update'] = mode
        self._modules: dict[str, ModuleNode] = {}
        self._cr: BaseCursor = cr

    def __contains__(self, name: str) -> bool:
        return name in self._modules

    def __getitem__(self, name: str) -> ModuleNode:
        return self._modules[name]

    def __iter__(self) -> Iterator[ModuleNode]:
        return iter(sorted(self._modules.values(), key=lambda p: (p.phase, p.depth, p.order_name)))

    def __len__(self) -> int:
        return len(self._modules)

    def extend(self, names: Collection[str]) -> None:
        for module in self._modules.values():
            reset_cached_properties(module)

        names = [name for name in names if name not in self._modules]

        for name in names:
            module = self._modules[name] = ModuleNode(name, self)
            if not module.manifest.get('installable'):
                if name in self._imported_modules:
                    self._remove(name, log_dependents=False)
                else:
                    _logger.warning('module %s: not installable, skipped', name)
                    self._remove(name)

        self._update_depends(names)
        self._update_depth(names)
        self._update_from_database(names)

    @functools.cached_property
    def _imported_modules(self) -> OrderedSet[str]:
        result = ['studio_customization']
        if column_exists(self._cr, 'ir_module_module', 'imported'):
            self._cr.execute('SELECT name FROM ir_module_module WHERE imported')
            result += [m[0] for m in self._cr.fetchall()]
        return OrderedSet(result)

    def _update_depends(self, names: Iterable[str]) -> None:
        for name in names:
            if module := self._modules.get(name):
                depends = module.manifest['depends']
                try:
                    module.depends = OrderedSet(self._modules[dep] for dep in depends)
                except KeyError:
                    _logger.info('module %s: some depends are not loaded, skipped', name)
                    self._remove(name)

    def _update_depth(self, names: Iterable[str]) -> None:
        for name in names:
            if module := self._modules.get(name):
                try:
                    module.depth
                except RecursionError:
                    _logger.warning('module %s: in a dependency loop, skipped', name)
                    self._remove(name)

    def _update_from_database(self, names: Iterable[str]) -> None:
        names = tuple(name for name in names if name in self._modules)
        if not names:
            return
        # update modules with values from the database (if exist)
        query = '''
            SELECT name, id, state, demo, latest_version AS installed_version
            FROM ir_module_module
            WHERE name IN %s
        '''
        self._cr.execute(query, [names])
        for name, id_, state, demo, installed_version in self._cr.fetchall():
            if state == 'uninstallable':
                _logger.warning('module %s: not installable, skipped', name)
                self._remove(name)
                continue
            if self.mode == 'load' and state in ['to install', 'uninstalled']:
                _logger.info('module %s: not installed, skipped', name)
                self._remove(name)
                continue
            if name not in self._modules:
                # has been recursively removed for sake of not installable or not installed
                continue
            module = self._modules[name]
            module.id = id_
            module.state = state
            module.demo = demo
            module.installed_version = installed_version
            module.load_version = installed_version
            module.load_state = state

    def _remove(self, name: str, log_dependents: bool = True) -> None:
        module = self._modules.pop(name)
        for another, another_module in list(self._modules.items()):
            if module in another_module.depends and another_module.name in self._modules:
                if log_dependents:
                    _logger.info('module %s: its direct/indirect dependency is skipped, skipped', another)
                self._remove(another)
