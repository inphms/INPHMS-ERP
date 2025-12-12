from __future__ import annotations
import os

from inphms.config import config
from ._vendor.which import which

__all__ = ["find_in_path", 'find_pg_tool', "exec_pg_environ"]


def find_in_path(name):
    path = os.environ.get('PATH', os.defpath).split(os.pathsep)
    if config.get('bin_path') and config['bin_path'] != 'None':
        path.append(config['bin_path'])
    return which(name, path=os.pathsep.join(path))


def find_pg_tool(name):
    path = None
    if config['pg_path'] and config['pg_path'] != 'None':
        path = config['pg_path']
    try:
        return which(name, path=path)
    except OSError:
        raise Exception('Command `%s` not found.' % name)


def exec_pg_environ():
    """
    Force the database PostgreSQL environment variables to the database
    configuration of Inphms.

    Note: On systems where pg_restore/pg_dump require an explicit password
    (i.e.  on Windows where TCP sockets are used), it is necessary to pass the
    postgres user password in the PGPASSWORD environment variable or in a
    special .pgpass file.

    See also https://www.postgresql.org/docs/current/libpq-envars.html
    """
    env = os.environ.copy()
    if config['db_host']:
        env['PGHOST'] = config['db_host']
    if config['db_port']:
        env['PGPORT'] = str(config['db_port'])
    if config['db_user']:
        env['PGUSER'] = config['db_user']
    if config['db_password']:
        env['PGPASSWORD'] = config['db_password']
    if config['db_appname']:
        env['PGAPPNAME'] = config['db_appname'].replace('{pid}', f'env{os.getpid()}')[:63]
    if config['db_sslmode']:
        env['PGSSLMODE'] = config['db_sslmode']
    return env