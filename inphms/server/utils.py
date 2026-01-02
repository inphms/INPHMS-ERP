from __future__ import annotations
from itertools import groupby
import platform
import sys
import threading
import logging
import traceback
import werkzeug
import werkzeug.local
import time
import typing as t
import psycopg2
import re
import contextlib
import os

if os.name == 'posix':
    import resource

from inspect import signature, Parameter

import inphms.service.db
from inphms import config
from inphms.tools import exception_to_unicode, profiler
from inphms.databases import db_connect, sql_counter
from inphms.modules import Registry, Environment, SUPERUSER_ID

if t.TYPE_CHECKING:
    from .request import Request
    from collections.abc import Callable

_logger = logging.getLogger("inphms.server.http")

server_phoenix = False

thread_local = threading.local()
thread_local.rpc_model_method = ''
SLEEP_INTERVAL = 60 # seconds

DEFAULT_LANG = 'en_US'
DEFAULT_MAX_CONTENT_LENGTH = 128 * 1024 * 1024  # 128MiB
STATIC_CACHE = 60 * 60 * 24 * 7
STATIC_CACHE_LONG = 60 * 60 * 24 * 365


def strip_sys_argv(*strip_args):
    strip_args = sorted(set(strip_args) | set(['-s', '--save',]))
    assert all(config.parser.has_option(a) for a in strip_args)
    takes_value = dict((a, config.parser.get_option(a).takes_value()) for a in strip_args)
    long, short = list(tuple(y) for _, y in groupby(strip_args, lambda x: x.startswith('--')))
    long_eq = tuple(lo + '=' for lo in long if takes_value[lo])
    args = sys.argv[:]
    def _strip(args, i):
        return args[i].startswith(short) \
            or args[i].startswith(long_eq) or (args[i] in long) \
            or (i >= 1 and (args[i-1] in strip_args) and takes_value[args[i-1]])
    
    return [a for i, a in enumerate(args) if not _strip(args, i)]


def memory_info(process):
    """ Return memory info for a process.
    """
    # psutil < 2.0 does not have memory_info, >= 3.0 does not have get_memory_info
    pmem = (getattr(process, 'memory_info', None) or process.get_memory_info)()
    if platform.system() == 'Darwin':
        return pmem.rss # RESIDENT SET SIZE
    return pmem.vms # VIRTUAL MEMORY SIZE


def set_limit_memory_hard():
    if platform.system() != 'linux':
        return
    limit_memory_hard = config['limit_memory_hard']
    if limit_memory_hard:
        rlimit = resource.RLIMIT_AS
        soft, hard = resource.getrlimit(rlimit)
        resource.setrlimit(rlimit, (limit_memory_hard, hard))


_request_stack = werkzeug.local.LocalStack() # type: ignore
request: Request = _request_stack()  # type: ignore

@contextlib.contextmanager
def borrow_request():
    """ Get the current request and unexpose it from the local stack. """
    req = _request_stack.pop()
    try:
        yield req
    finally:
        _request_stack.push(req)


######################
# Security utilities #
######################
MISSING_CSRF_WARNING = """\
No CSRF validation token provided for path %r

Inphms URLs are CSRF-protected by default (when accessed with unsafe
HTTP methods).

* if this endpoint is accessed through Inphms via QWeb form, embed a CSRF
  token in the form, Tokens are available via `request.csrf_token()`
  can be provided through a hidden input and must be POST-ed named
  `csrf_token` e.g. in your form add:
      <input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>

* if the form is generated or posted in javascript, the token value is
  available as `csrf_token` on `web.core` and as the `csrf_token`
  value in the default js-qweb execution context

* if the form is accessed by an external third party (e.g. REST API
  endpoint, payment gateway callback) you will need to disable CSRF
  protection (and implement your own protection if necessary) by
  passing the `csrf=False` parameter to the `route` decorator.
"""

CORS_MAX_AGE = 60 * 60 * 24
CSRF_TOKEN_SALT = 60 * 60 * 24 * 365
SAFE_HTTP_METHODS = ('GET', 'HEAD', 'OPTIONS', 'TRACE')

def is_cors_preflight(request, endpoint):
    return request.httprequest.method == 'OPTIONS' and endpoint.routing.get('cors', False)

def filter_kwargs(func: Callable, kwargs: dict[str, t.Any]) -> dict[str, t.Any]:
    """ Return a copy of ``kwargs`` with only the arguments accepted by ``func``. """
    leftovers = set(kwargs)
    for p in signature(func).parameters.values():
        if p.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY):
            leftovers.discard(p.name)
        elif p.kind == Parameter.VAR_KEYWORD:  # **kwargs
            leftovers.clear()
            break

    if not leftovers:
        return kwargs

    return {key: kwargs[key] for key in kwargs if key not in leftovers}


#######################
# Exception utilities #
#######################
def serialize_exception(exception, *, message=None, arguments=None):
    name = type(exception).__name__
    module = type(exception).__module__

    return {
        'name': f'{module}.{name}' if module else name,
        'message': exception_to_unicode(exception) if message is None else message,
        'arguments': exception.args if arguments is None else arguments,
        'context': getattr(exception, 'context', {}),
        'debug': ''.join(traceback.format_exception(exception)),
    }


#####################
# Session utilities #
#####################
SESSION_ROTATION_INTERVAL = 60 * 60 * 3
SESSION_LIFETIME = 60 * 60 * 24 * 7
SESSION_DELETION_TIMER = 120
STORED_SESSION_BYTES = 42
def get_default_session():
    return {'context': {},
            'create_time': time.time(),
            'db': None,
            'debug': '',
            'login': None,
            'uid': None,
            'session_token': None,
            '_trace': [],}

def get_session_max_inactivity(env):
    if not env or env.cr._closed:
        return SESSION_LIFETIME

    ICP = env['ir.config_parameter'].sudo()
    try:
        return int(ICP.get_param('sessions.max_inactivity_seconds', SESSION_LIFETIME))
    except ValueError:
        _logger.warning("Invalid value for 'sessions.max_inactivity_seconds', using default value.")
        return SESSION_LIFETIME


#################
# DB utilities  #
#################
NOT_FOUND_NODB = """\
<!DOCTYPE html>
<title>404 Not Found</title>
<h1>Not Found</h1>
<p>No database is selected and the requested URL was not found in the server-wide controllers.</p>
<p>Please verify the hostname, <a href=/web/login>login</a> and try again.</p>

<!-- Alternatively, use the X-Inphms-Database header. -->
"""

def db_list(force=False, host=None):
    """ Get the list of available databases. """
    try:
        dbs = inphms.service.db.list_dbs(force)
    except psycopg2.OperationalError:
        return []
    return db_filter(dbs, host)

def db_filter(dbs, host=None):
    """ Return the subset of ``dbs`` that match the dbfilter or the dbname
        server configuration.
    """

    if config['dbfilter']:
        #        host
        #     -----------
        # www.example.com:80
        #     -------
        #     domain
        if host is None:
            host = request.httprequest.environ.get('HTTP_HOST', '')
        host = host.partition(':')[0]
        if host.startswith('www.'):
            host = host[4:]
        domain = host.partition('.')[0]

        dbfilter_re = re.compile(
            config["dbfilter"].replace("%h", re.escape(host))
                              .replace("%d", re.escape(domain)))
        return [db for db in dbs if dbfilter_re.match(db)]

    if config['db_list']:
        return sorted(set(config['db_list']).intersection(dbs))

    return list(dbs)

def cron_database_list():
    return config['db_list'] or inphms.service.db.list_dbs(True)


##############
# Registries #
##############
def preload_registries(dbnames):
    dbnames = dbnames or []
    rc = 0

    preload_profiler = contextlib.nullcontext()
    for dbname in dbnames:
        if os.environ.get('INPHMS_PROFILE_PRELOAD'):
            interval = float(os.environ.get('INPHMS_PROFILE_PRELOAD_INTERVAL', '0.1'))
            collectors = [profiler.PeriodicCollector(interval=interval)]
            if os.environ.get('INPHMS_PROFILE_PRELOAD_SQL'):
                collectors.append('sql')
            preload_profiler = profiler.Profiler(db=dbname, collectors=collectors)
        try:
            with preload_profiler:
                threading.current_thread().dbname = dbname
                update_module = config['init'] or config['update'] or config['reinit']
                
                registry = Registry.new(dbname, update_module=update_module, install_modules=config['init'], upgrade_modules=config['update'], reinit_modules=config['reinit'])
                
                # run post-install tests
                if config['test_enable']:
                    from inphms.tests import loader  # noqa: PLC0415
                    t0 = time.time()
                    t0_sql = sql_counter
                    module_names = (registry.updated_modules if update_module else
                                    sorted(registry._init_modules))
                    _logger.info("Starting post tests")
                    tests_before = registry._assertion_report.testsRun
                    post_install_suite = loader.make_suite(module_names, 'post_install')
                    if post_install_suite.has_http_case():
                        with registry.cursor() as cr:
                            env = Environment(cr, SUPERUSER_ID, {})
                            env['ir.qweb']._pregenerate_assets_bundles()
                    result = loader.run_suite(post_install_suite, global_report=registry._assertion_report)
                    registry._assertion_report.update(result)
                    _logger.info("%d post-tests in %.2fs, %s queries",
                                registry._assertion_report.testsRun - tests_before,
                                time.time() - t0,
                                sql_counter - t0_sql)

                    registry._assertion_report.log_stats()
                if registry._assertion_report and not registry._assertion_report.wasSuccessful():
                    rc += 1
        except Exception:
            _logger.critical('Failed to initialize database `%s`.', dbname, exc_info=True)
            return -1
    return rc