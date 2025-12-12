from __future__ import annotations
import typing as t
import os
import ast
import copy
import functools
import inphms.addons
import logging

from os.path import join as opj, isdir
from collections.abc import Mapping

from .utils import MODULE_NAME_RE, README, MANIFEST_NAMES, _load_manifest, adapt_version, get_module_icon, check_python_external_dependency
from inphms.exceptions import MissingDependency
from inphms import tools

if t.TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

@t.final
class Manifest(Mapping[str, t.Any]):
    """The manifest data of a module."""

    def __init__(self, *, path: str, manifest_content: dict):
        assert os.path.isabs(path), "path of module must be absolute"
        self.path = path
        _, self.name = os.path.split(path)
        if not MODULE_NAME_RE.match(self.name):
            raise FileNotFoundError(f"Invalid module name: {self.name}")
        self.__manifest_content = manifest_content

    @property
    def addons_path(self) -> str:
        parent_path, name = os.path.split(self.path)
        assert name == self.name
        return parent_path

    @functools.cached_property
    def __manifest_cached(self) -> dict:
        """Parsed and validated manifest data from the file."""
        return _load_manifest(self.name, self.__manifest_content)

    @functools.cached_property
    def description(self):
        """The description of the module defaulting to the README file."""
        if (desc := self.__manifest_cached.get('description')):
            return desc
        for file_name in README:
            try:
                with tools.file_open(opj(self.path, file_name)) as f:
                    return f.read()
            except OSError:
                pass
        return ''

    @functools.cached_property
    def version(self):
        try:
            return self.__manifest_cached['version']
        except Exception:
            return adapt_version('1.0')

    @functools.cached_property
    def icon(self) -> str:
        return get_module_icon(self.name)

    @functools.cached_property
    def static_path(self) -> str | None:
        static_path = opj(self.path, 'static')
        manifest = self.__manifest_cached
        if (manifest['installable'] or manifest['assets']) and isdir(static_path):
            return static_path
        return None

    def __getitem__(self, key: str):
        if key in ('description', 'icon', 'addons_path', 'version', 'static_path'):
            return getattr(self, key)
        return copy.deepcopy(self.__manifest_cached[key])

    def raw_value(self, key):
        return copy.deepcopy(self.__manifest_cached.get(key))

    def __iter__(self):
        manifest = self.__manifest_cached
        yield from manifest
        for key in ('description', 'icon', 'addons_path', 'version', 'static_path'):
            if key not in manifest:
                yield key

    def check_manifest_dependencies(self) -> None:
        """ Check that the dependecies of the manifest are available.

            - Checking for external python dependencies
            - Checking binaries are available in PATH

            On missing dependencies, raise an error.
        """
        depends = self.get('external_dependencies')
        if not depends:
            return
        for pydep in depends.get('python', []):
            check_python_external_dependency(pydep)

        for binary in depends.get('bin', []):
            try:
                tools.find_in_path(binary)
            except OSError:
                msg = "Unable to find {dependency!r} in path"
                raise MissingDependency(msg, binary)

    def __bool__(self):
        return True

    def __len__(self):
        return sum(1 for _ in self)

    def __repr__(self):
        return f'Manifest({self.name})'

    # limit cache size because this may get called from any module with any input
    @staticmethod
    @functools.lru_cache(10_000)
    def _get_manifest_from_addons(module: str) -> Manifest | None:
        """Get the module's manifest from a name. Searching only in addons paths."""
        for adp in inphms.addons.__path__:
            if manifest := Manifest._from_path(opj(adp, module)):
                return manifest
        return None

    @staticmethod
    def for_addon(module_name: str, *, display_warning: bool = True) -> Manifest | None:
        """ Get the module's manifest from a name.

            :param module: module's name
            :param display_warning: log a warning if the module is not found
        """
        if not MODULE_NAME_RE.match(module_name):
            # invalid module name
            return None
        if mod := Manifest._get_manifest_from_addons(module_name):
            return mod
        if display_warning:
            _logger.warning('module %s: manifest not found', module_name)
        return None

    @staticmethod
    def _from_path(path: str, env=None) -> Manifest | None:
        """Given a path, read the manifest file."""
        for manifest_name in MANIFEST_NAMES:
            try:
                with tools.file_open(opj(path, manifest_name), env=env) as f:
                    manifest_content = ast.literal_eval(f.read())
            except OSError:
                pass
            except Exception:
                _logger.debug("Failed to parse the manifest file at %r", path, exc_info=True)
            else:
                return Manifest(path=path, manifest_content=manifest_content)
        return None

    @staticmethod
    def all_addon_manifests() -> list[Manifest]:
        """Read all manifests in the addons paths."""
        modules: dict[str, Manifest] = {}
        for adp in inphms.addons.__path__:
            if not os.path.isdir(adp):
                _logger.warning("addons path is not a directory: %s", adp)
                continue
            for file_name in os.listdir(adp):
                if file_name in modules:
                    continue
                if mod := Manifest._from_path(opj(adp, file_name)):
                    assert file_name == mod.name
                    modules[file_name] = mod
        return sorted(modules.values(), key=lambda m: m.name)
