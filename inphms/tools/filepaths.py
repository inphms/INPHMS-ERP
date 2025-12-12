from __future__ import annotations
import os
import sys
import typing as t
import tempfile

from contextlib import contextmanager
from os.path import normpath, normcase, isfile, abspath, dirname, join as opj, isabs

import inphms.addons

if t.TYPE_CHECKING:
    from inphms.modules import Environment


__all__ = ['file_path', 'file_open', 'file_open_temporary_directory']


def file_path(file_path: str, filter_ext: tuple[str, ...] = ('',), env: Environment | None = None, *, check_exists: bool = True) -> str:
    """ Verify that a file exists under a known `addons_path` directory and return its full path.

        Examples::

        >>> file_path('hr')
        >>> file_path('hr/static/description/icon.png')
        >>> file_path('hr/static/description/icon.png', filter_ext=('.png', '.jpg'))
    """
    is_abs = isabs(file_path)
    normalized_path = normpath(normcase(file_path))

    if filter_ext and not normalized_path.lower().endswith(filter_ext):
        raise ValueError("Unsupported file: " + file_path)

    file_path_split = normalized_path.split(os.path.sep)
    if not is_abs and (module := sys.modules.get(f'inphms.addons.{file_path_split[0]}')):
        addons_paths = list(map(dirname, module.__path__))
    else:
        from inphms.config import config
        root_path = abspath(config.root_path)
        temporary_paths = env.transaction._Transaction__file_open_tmp_paths if env else ()
        addons_paths = [*inphms.addons.__path__, root_path, *temporary_paths]

    for addons_dir in addons_paths:
        parent_path = normpath(normcase(addons_dir)) + os.sep
        if is_abs:
            fpath = normalized_path
        else:
            fpath = normpath(opj(parent_path, normalized_path))
        if fpath.startswith(parent_path) and (
            (not check_exists and (is_abs or len(addons_paths) == 1))
            or os.path.exists(fpath)
        ):
            return fpath

    raise FileNotFoundError("File not found: " + file_path)


def file_open(name: str, mode: str = "r", filter_ext: tuple[str, ...] = (), env: Environment | None = None):
    """ Open a file from within the addons_path directories, as an absolute or relative path.

        Examples::

            >>> file_open('hr/static/description/icon.png')
            >>> file_open('hr/static/description/icon.png', filter_ext=('.png', '.jpg'))
            >>> with file_open('/opt/inphms/addons/hr/static/description/icon.png', 'rb') as f:
            ...     contents = f.read()
    """
    path = file_path(name, filter_ext=filter_ext, env=env, check_exists=False)
    encoding = None
    if 'b' not in mode:
        encoding = "utf-8"
    if any(m in mode for m in ('w', 'x', 'a')) and not isfile(path):
        # Don't let create new files
        raise FileNotFoundError(f"Not a file: {path}")
    return open(path, mode, encoding=encoding)



@contextmanager
def file_open_temporary_directory(env: Environment):
    """Create and return a temporary directory added to the directories `file_open` is allowed to read from.

    `file_open` will be allowed to open files within the temporary directory
    only for environments of the same transaction than `env`.
    Meaning, other transactions/requests from other users or even other databases
    won't be allowed to open files from this directory.

    Examples::

        >>> with inphms.tools.file_open_temporary_directory(self.env) as module_dir:
        ...    with zipfile.ZipFile('foo.zip', 'r') as z:
        ...        z.extract('foo/__manifest__.py', module_dir)
        ...    with inphms.tools.file_open('foo/__manifest__.py', env=self.env) as f:
        ...        manifest = f.read()

    :param env: environment for which the temporary directory is created.
    :return: the absolute path to the created temporary directory
    """
    assert not env.transaction._Transaction__file_open_tmp_paths, 'Reentrancy is not implemented for this method'
    with tempfile.TemporaryDirectory() as module_dir:
        try:
            env.transaction._Transaction__file_open_tmp_paths = (module_dir,)
            yield module_dir
        finally:
            env.transaction._Transaction__file_open_tmp_paths = ()
