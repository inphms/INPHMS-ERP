from __future__ import annotations
import re
import copy
import logging
import importlib
import importlib.metadata
import os
import inphms.addons

from collections.abc import Collection, Iterable
from packaging.requirements import InvalidRequirement, Requirement

from inphms import tools, release
from inphms.exceptions import MissingDependency
from inphms.tools import frozendict

_logger = logging.getLogger(__name__)

EMPTY_DICT: frozendict = frozendict()

SUPERUSER_ID = 1
MAX_FIXPOINT_ITERATIONS = 10

MODULE_NAME_RE = re.compile(r'^\w{1,256}$')
MANIFEST_NAMES = ['__manifest__.py']
README = ['README.rst', 'README.md', 'README.txt', 'README']
_DEFAULT_MANIFEST = {
    # Mandatory fields (with no defaults):
    # - author
    # - license
    # - name
    # Derived fields are computed in the Manifest class.
    'application': False,
    'bootstrap': False,  # web
    'assets': {},
    'auto_install': False,
    'category': 'Uncategorized',
    'cloc_exclude': [],
    'configurator_snippets': {},  # website themes
    'configurator_snippets_addons': {},  # website themes
    'countries': [],
    'data': [],
    'demo': [],
    'demo_xml': [],
    'depends': [],
    'description': '',  # defaults to README file
    'external_dependencies': {},
    'init_xml': [],
    'installable': True,
    'images': [],  # website
    'images_preview_theme': {},  # website themes
    'live_test_url': '',  # website themes
    'new_page_templates': {},  # website themes
    'post_init_hook': '',
    'post_load': '',
    'pre_init_hook': '',
    'sequence': 100,
    'summary': '',
    'test': [],
    'theme_customizations': {},  # themes
    'update_xml': [],
    'uninstall_hook': '',
    'version': '1.0',
    'web': False,
    'website': '',
}

# matches field definitions like
#     partner_id: base.ResPartner = fields.Many2one
#     partner_id = fields.Many2one[base.ResPartner]
TYPED_FIELD_DEFINITION_RE = re.compile(r'''
    \b (?P<field_name>\w+) \s*
    (:\s*(?P<field_type>[^ ]*))? \s*
    = \s*
    fields\.(?P<field_class>Many2one|One2many|Many2many)
    (\[(?P<type_param>[^\]]+)\])?
''', re.VERBOSE)


def get_module_icon(module: str) -> str:
    from . import Manifest
    """ Get the path to the module's icon. Invalid module names are accepted. """
    manifest = Manifest.for_addon(module, display_warning=False)
    if manifest and 'icon' in manifest.__dict__:
        return manifest.icon
    try:
        fpath = f"{module}/static/description/icon.png"
        tools.file_path(fpath)
        return "/" + fpath
    except FileNotFoundError:
        return "/base/static/description/icon.png"


def _load_manifest(module: str, manifest_content: dict) -> dict:
    """ Load and validate the module manifest.

        Return a new dictionary with cleaned and validated keys.
    """
    manifest = copy.deepcopy(_DEFAULT_MANIFEST)
    manifest.update(manifest_content)

    if not manifest.get('author'):
        # Altought contributors and maintainer are not documented, it is
        # not uncommon to find them in manifest files, use them as
        # alternative.
        author = manifest.get('contributors') or manifest.get('maintainer') or ''
        manifest['author'] = str(author)
        _logger.warning("Missing `author` key in manifest for %r, defaulting to %r", module, str(author))

    if not manifest.get('license'):
        manifest['license'] = 'LGPL-3'
        _logger.warning("Missing `license` key in manifest for %r, defaulting to LGPL-3", module)

    if module == 'base':
        manifest['depends'] = []
    elif not manifest['depends']:
        # prevent the hack `'depends': []` except 'base' module
        manifest['depends'] = ['base']

    depends = manifest['depends']
    assert isinstance(depends, Collection)

    # auto_install is either `False` (by default) in which case the module
    # is opt-in, either a list of dependencies in which case the module is
    # automatically installed if all dependencies are (special case: [] to
    # always install the module), either `True` to auto-install the module
    # in case all dependencies declared in `depends` are installed.
    if isinstance(manifest['auto_install'], Iterable):
        manifest['auto_install'] = auto_install_set = set(manifest['auto_install'])
        non_dependencies = auto_install_set.difference(depends)
        assert not non_dependencies, (
            "auto_install triggers must be dependencies,"
            f" found non-dependencies [{', '.join(non_dependencies)}] for module {module}"
        )
    elif manifest['auto_install']:
        manifest['auto_install'] = set(depends)

    try:
        manifest['version'] = adapt_version(str(manifest['version']))
    except ValueError as e:
        if manifest['installable']:
            raise ValueError(f"Module {module}: invalid manifest") from e
    if manifest['installable'] and not check_version(str(manifest['version']), should_raise=False):
        _logger.warning("The module %s has an incompatible version, setting installable=False", module)
        manifest['installable'] = False

    return manifest


def adapt_version(version: str) -> str:
    """Reformat the version of the module into a canonical format."""
    version_str_parts = version.split('.')
    if not (2 <= len(version_str_parts) <= 5):
        raise ValueError(f"Invalid version {version!r}, must have between 2 and 5 parts")
    serie = release.MAJOR
    if version.startswith(serie) and not version_str_parts[0].isdigit():
        # keep only digits for parsing
        version_str_parts[0] = ''.join(c for c in version_str_parts[0] if c.isdigit())
    try:
        version_parts = [int(v) for v in version_str_parts]
    except ValueError as e:
        raise ValueError(f"Invalid version {version!r}") from e
    if len(version_parts) <= 3 and not version.startswith(serie):
        # prefix the version with serie
        return f"{serie}.{version}"
    return version


def check_version(version: str, should_raise: bool = True) -> bool:
    """Check that the version is in a valid format for the current release."""
    version = adapt_version(version)
    serie = release.MAJOR
    if version.startswith(serie + '.'):
        return True
    if should_raise:
        raise ValueError(
            f"Invalid version {version!r}. Modules should have a version in format"
            f" `x.y`, `x.y.z`, `{serie}.x.y` or `{serie}.x.y.z`.")
    return False


def check_python_external_dependency(pydep: str) -> None:
    try:
        requirement = Requirement(pydep)
    except InvalidRequirement as e:
        msg = f"{pydep} is an invalid external dependency specification: {e}"
        raise ValueError(msg) from e
    if requirement.marker and not requirement.marker.evaluate():
        _logger.debug(
            "Ignored external dependency %s because environment markers do not match",
            pydep
        )
        return
    try:
        version = importlib.metadata.version(requirement.name)
    except importlib.metadata.PackageNotFoundError as e:
        try:
            # keep compatibility with module name but log a warning instead of info
            importlib.import_module(pydep)
            _logger.warning("python external dependency on '%s' does not appear o be a valid PyPI package. Using a PyPI package name is recommended.", pydep)
            return
        except ImportError:
            pass
        msg = "External dependency {dependency!r} not installed: %s" % (e,)
        raise MissingDependency(msg, pydep) from e
    if requirement.specifier and not requirement.specifier.contains(version):
        msg = f"External dependency version mismatch: {{dependency}} (installed: {version})"
        raise MissingDependency(msg, pydep)


def load_script(path: str, module_name: str):
    full_path = tools.file_path(path) if not os.path.isabs(path) else path
    spec = importlib.util.spec_from_file_location(module_name, full_path)
    assert spec and spec.loader, f"spec not found for {module_name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# cache invalidation dependencies, as follows:
# { 'cache_key': ('cache_container_1', 'cache_container_3', ...) }
_CACHES_BY_KEY = {
    'default': ('default', 'templates.cached_values'),
    'assets': ('assets', 'templates.cached_values'),
    'stable': ('stable', 'default', 'templates.cached_values'),
    'templates': ('templates', 'templates.cached_values'),
    'routing': ('routing', 'routing.rewrites', 'templates.cached_values'),
    'groups': ('groups', 'templates', 'templates.cached_values'),  # The processing of groups is saved in the view
}

_REGISTRY_CACHES = {
    'default': 8192,
    'assets': 512,
    'stable': 1024,
    'templates': 1024,
    'routing': 1024,  # 2 entries per website
    'routing.rewrites': 8192,  # url_rewrite entries
    'templates.cached_values': 2048,  # arbitrary
    'groups': 8,  # see res.groups
}


_REPLICA_RETRY_TIME = 20 * 60  # 20 minutes


def get_resource_from_path(path: str) -> tuple[str, str, str] | None:
    """Tries to extract the module name and the resource's relative path
    out of an absolute resource path.

    If operation is successful, returns a tuple containing the module name, the relative path
    to the resource using '/' as filesystem seperator[1] and the same relative path using
    os.path.sep seperators.

    [1] same convention as the resource path declaration in manifests

    :param path: absolute resource path

    :rtype: tuple
    :return: tuple(module_name, relative_path, os_relative_path) if possible, else None
    """
    resource = None
    sorted_paths = sorted(inphms.addons.__path__, key=len, reverse=True)
    for adpath in sorted_paths:
        # force trailing separator
        adpath = os.path.join(adpath, "")
        if os.path.commonprefix([adpath, path]) == adpath:
            resource = path.replace(adpath, "", 1)
            break

    if resource:
        relative = resource.split(os.path.sep)
        if not relative[0]:
            relative.pop(0)
        module = relative.pop(0)
        return (module, '/'.join(relative), os.path.sep.join(relative))
    return None


class DummyRLock(object):
    """ Dummy reentrant lock, to be used while running rpc and js tests """
    def acquire(self):
        pass
    def release(self):
        pass
    def __enter__(self):
        self.acquire()
    def __exit__(self, type, value, traceback):
        self.release()
