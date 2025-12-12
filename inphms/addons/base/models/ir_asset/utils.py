from __future__ import annotations
import logging
import os

from glob import glob
from werkzeug import urls

from ..utils import ASSET_EXTENSIONS

_logger = logging.getLogger(__name__)

DEFAULT_SEQUENCE = 16

# Directives are stored in variables for ease of use and syntax checks.
APPEND_DIRECTIVE = 'append'
PREPEND_DIRECTIVE = 'prepend'
AFTER_DIRECTIVE = 'after'
BEFORE_DIRECTIVE = 'before'
REMOVE_DIRECTIVE = 'remove'
REPLACE_DIRECTIVE = 'replace'
INCLUDE_DIRECTIVE = 'include'
# Those are the directives used with a 'target' argument/field.
DIRECTIVES_WITH_TARGET = [AFTER_DIRECTIVE, BEFORE_DIRECTIVE, REPLACE_DIRECTIVE]


def fs2web(path):
    """Converts a file system path to a web path"""
    if os.path.sep == '/':
        return path
    return '/'.join(path.split(os.path.sep))


def can_aggregate(url):
    parsed = urls.url_parse(url)
    return not parsed.scheme and not parsed.netloc and not url.startswith('/web/content')


def is_wildcard_glob(path):
    """Determine whether a path is a wildcarded glob eg: "/web/file[14].*"
    or a genuine single file path "/web/myfile.scss"""
    return '*' in path or '[' in path or ']' in path or '?' in path


def _glob_static_file(pattern):
    files = glob(pattern, recursive=True)
    return sorted((file, os.path.getmtime(file)) for file in files if file.rsplit('.', 1)[-1] in ASSET_EXTENSIONS)


################
# CLASS HELPER #
################
class AssetPaths:
    """ A list of asset paths (path, addon, bundle) with efficient operations. """
    def __init__(self):
        self.list = []
        self.memo = set()

    def index(self, path, bundle):
        """Returns the index of the given path in the current assets list."""
        if path not in self.memo:
            self._raise_not_found(path, bundle)
        for index, asset in enumerate(self.list):
            if asset[0] == path:
                return index

    def append(self, paths, bundle):
        """Appends the given paths to the current list."""
        for path, full_path, last_modified in paths:
            if path not in self.memo:
                self.list.append((path, full_path, bundle, last_modified))
                self.memo.add(path)

    def insert(self, paths, bundle, index):
        """Inserts the given paths to the current list at the given position."""
        to_insert = []
        for path, full_path, last_modified in paths:
            if path not in self.memo:
                to_insert.append((path, full_path, bundle, last_modified))
                self.memo.add(path)
        self.list[index:index] = to_insert

    def remove(self, paths_to_remove, bundle):
        """Removes the given paths from the current list."""
        paths = {path for path, _full_path, _last_modified in paths_to_remove if path in self.memo}
        if paths:
            self.list[:] = [asset for asset in self.list if asset[0] not in paths]
            self.memo.difference_update(paths)
            return

        if paths_to_remove:
            self._raise_not_found([path for path, _full_path, _last_modified in paths_to_remove], bundle)

    def _raise_not_found(self, path, bundle):
        raise ValueError("File(s) %s not found in bundle %s" % (path, bundle))
