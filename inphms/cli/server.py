from __future__ import annotations

import atexit
import logging
import os
import sys
import inphms

from psycopg2.errors import InsufficientPrivilege

from inphms import config, release
from inphms.server import serving

from . import Command

_logger = logging.getLogger("inphms")


class Server(Command):
    """ Start the Inphms main server (default command) """

    def run(self, args:list[str]) -> None:
        Server.main(args)

    @classmethod
    def main(cls, args:list[str]) -> None:
        config.parse_config(args)
        cls.report_config()

        from inphms.service import db  # noqa: PLC0415
        for db_name in config['db_list']:
            try:
                db._create_empty_database(db_name)
                config['init']['base'] = True
            except InsufficientPrivilege as err:
                # We use an INFO loglevel on purpose in order to avoid
                # reporting unnecessary warnings on build environment
                # using restricted database access.
                _logger.info("Could not determine if database %s exists, "
                            "skipping auto-creation: %s", db_name, err)
            except db.DatabaseExists:
                pass

        stop = config["stop_after_init"]

        cls.setup_pid()
        rc = serving.start(preload=config['db_list'], stop=stop)
        sys.exit(rc)

    @classmethod
    def report_config(cls) -> None: 
        _logger.info(f"Inphms Version {release.VERSION}")
        if os.path.isfile(config['config_file']):
            _logger.info(f"Using Config file at {config['config_file']}")
        _logger.info("Addons path: %s", inphms.addons.__path__)
        host = config['db_host'] or os.environ.get('PGHOST', 'default')
        port = config['db_port'] or os.environ.get("PGPORT", "default")
        user = config['db_user'] or os.environ.get('PGUSER', 'default')
        _logger.info(f"Connecting to database {user}@{host}:{port}")
        replica_host = config['db_replica_host']
        replica_port = config['db_replica_port']
        if replica_host or replica_port or 'replica' in config['dev_mode']:
            _logger.info('replica database: %s@%s:%s', user, replica_host or 'default', replica_port or 'default')
        if sys.version_info[:2] > release.MAX_PY_VERSION:
            _logger.warning(">>> Warning: Python version is higher than recommended for this version of Inphms")
        
    @classmethod
    def setup_pid(cls) -> None:
        if config['pidfile']:
            pid = os.getpid()
            with open(config['pidfile'], 'w') as fd:
                fd.write(str(pid))
            atexit.register(cls.remove_pid, pid)

    @classmethod
    def remove_pid(cls, pid:int) -> None:
        if config['pidfile'] and pid == os.getpid():
            try:
                os.unlink(config['pidfile'])
            except OSError:
                raise