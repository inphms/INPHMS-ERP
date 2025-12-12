from __future__ import annotations

import os
import zipfile
import re

if os.name != 'nt':
    def is_running_as_nt_service():
        return False
else:
    import win32service as ws
    import win32serviceutil as wsu
    from contextlib import contextmanager
    from inphms.release import NT_SERVICE_NAME

    def is_running_as_nt_service():
        @contextmanager
        def close_service(service):
            try:
                yield service
            finally:
                ws.CloseServiceHandle(service)
        try:
            with close_service(wsu.OpenSCManager(None, None, ws.SC_MANAGER_ALL_ACCESS)) as mgr:
                with close_service(wsu.SmartOpenService(mgr, NT_SERVICE_NAME, ws.SERVICE_ALL_ACCESS)) as svc:
                    status = ws.QueryServiceStatusEx(svc)
                    return status['ProcessId'] == os.getppid()
        except Exception:
            return False


def zip_dir(path, stream, include_dir=True, fnct_sort=None):      # TODO add ignore list
    """
    : param fnct_sort : Function to be passed to "key" parameter of built-in
                        python sorted() to provide flexibility of sorting files
                        inside ZIP archive according to specific requirements.
    """
    path = os.path.normpath(path)
    len_prefix = len(os.path.dirname(path)) if include_dir else len(path)
    if len_prefix:
        len_prefix += 1

    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
        for dirpath, _dirnames, filenames in os.walk(path):
            filenames = sorted(filenames, key=fnct_sort)
            for fname in filenames:
                bname, ext = os.path.splitext(fname)
                ext = ext or bname
                if ext not in ['.pyc', '.pyo', '.swp', '.DS_Store']:
                    path = os.path.normpath(os.path.join(dirpath, fname))
                    if os.path.isfile(path):
                        zipf.write(path, path[len_prefix:])


WINDOWS_RESERVED = re.compile(r'''
    ^
    # forbidden stems: reserved keywords
    (:?CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])
    # even with an extension this is recommended against
    (:?\..*)?
    $
''', flags=re.IGNORECASE | re.VERBOSE)
def clean_filename(name, replacement=''):
    """ Strips or replaces possibly problematic or annoying characters our of
    the input string, in order to make it a valid filename in most operating
    systems (including dropping reserved Windows filenames).

    If this results in an empty string, results in "Untitled" (localized).

    Allows:

    * any alphanumeric character (unicode)
    * underscore (_) as that's innocuous
    * dot (.) except in leading position to avoid creating dotfiles
    * dash (-) except in leading position to avoid annoyance / confusion with
      command options
    * brackets ([ and ]), while they correspond to shell *character class*
      they're a common way to mark / tag files especially on windows
    * parenthesis ("(" and ")"), a more natural though less common version of
      the former
    * space (" ")

    :param str name: file name to clean up
    :param str replacement:
        replacement string to use for sequences of problematic input, by default
        an empty string to remove them entirely, each contiguous sequence of
        problems is replaced by a single replacement
    :rtype: str
    """
    if WINDOWS_RESERVED.match(name):
        return "Untitled"
    return re.sub(r'[^\w_.()\[\] -]+', replacement, name).lstrip('.-') or "Untitled"
