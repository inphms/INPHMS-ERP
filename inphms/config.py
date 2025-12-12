from __future__ import annotations
import collections
import configparser
import errno
import functools
import optparse
import sys
import glob
import os
import logging

import typing as t
from os.path import isdir, join as opj, expanduser, expandvars, dirname, abspath, isfile, normcase, realpath

from passlib.context import CryptContext
ctx = CryptContext(schemes=['pbkdf2_sha512', 'plaintext'],
                             deprecated=['plaintext'],
                             pbkdf2_sha512__rounds=600_000)

from inphms import release
from inphms.tools import appdirs, classproperty

if t.TYPE_CHECKING:
    from collections.abc import Iterable

_dangerous_logger = logging.getLogger(__name__)


class _InphmsOption(optparse.Option):
    config = None

    TYPES: tuple[str, ...] = ('int', 'float', 'string', 'choice', 'bool', 'path', 'comma',
             'addons_path', 'upgrade_path', 'pre_upgrade_scripts', 'without_demo')

    @classproperty
    def TYPE_CHECKER(cls):
        return {
            'int': lambda _option, _opt, value: int(value),
            'float': lambda _option, _opt, value: float(value),
            'string': lambda _option, _opt, value: str(value),
            'choice': optparse.check_choice,
            'bool': cls.config._check_bool,
            'path': cls.config._check_path,
            'comma': cls.config._check_comma,
            'addons_path': cls.config._check_addons_path,
            'upgrade_path': cls.config._check_upgrade_path,
            'pre_upgrade_scripts': cls.config._check_scripts,
            'without_demo': cls.config._check_without_demo,
        }

    @classproperty
    def TYPE_FORMATTER(cls):
        return {
            'int': cls.config._format_string,
            'float': cls.config._format_string,
            'string': cls.config._format_string,
            'choice': cls.config._format_string,
            'bool': cls.config._format_string,
            'path': cls.config._format_string,
            'comma': cls.config._format_list,
            'addons_path': cls.config._format_list,
            'upgrade_path': cls.config._format_list,
            'pre_upgrade_scripts': cls.config._format_list,
            'without_demo': cls.config._format_without_demo,
        }

    def __init__(self, *opts, **attrs) -> None:
        self.my_default = attrs.pop("my_default", None)
        self.cli_loadable = attrs.pop("cli_loadable", True)
        env_name = attrs.pop("env_name", None)
        self.env_name = env_name or ''
        self.file_loadable = attrs.pop("file_loadable", True)
        self.file_exportable = attrs.pop("file_exportable", self.file_loadable)
        self.nargs_ = attrs.get('nargs')
        if self.nargs_ == '?':
            const = attrs.pop('const', None)
            attrs['nargs'] = 1
        attrs.setdefault('metavar', attrs.get('type', 'string').upper())
        super().__init__(*opts, **attrs)
        if self.file_exportable and not self.file_loadable:
            e = (f"it makes no sense that the option {self} can be exported "
                  "to the config file but not loaded from the config file")
            raise ValueError(e)
        is_new_option = False
        assert self.config is not None
        if self.dest and self.dest not in self.config.opts_index:
            self.config.opts_index[self.dest] = self
            is_new_option = True
        if self.nargs_ == '?':
            self.const = const
            for opt in self._short_opts + self._long_opts:
                self.config.opts_optional[opt] = self
        if env_name is None and is_new_option and self.file_loadable:
            self.env_name = f"INPHMS_{self.dest.upper()}"

    def __str__(self):
        out = []
        if self.cli_loadable:
            out.append(super().__str__())
        if self.file_loadable:
            out.append(self.dest)
        return '/'.join(out)
        

class _FileOnlyOption(_InphmsOption):
    def __init__(self, **attrs) -> None:
        super().__init__(**attrs, cli_loadable=False, help=optparse.SUPPRESS_HELP)
    
    def _check_opt_strings(self, opts: Iterable[str | None]) -> list:
        if opts:
            raise TypeError("File only options cannot take an argument")
        return []

    def _set_opt_strings(self, opts: Iterable[str]) -> None:
        return
    

class _PosixOnlyOption(_InphmsOption):
    def __init__(self, *opts, **attrs):
        if os.name != 'posix':
            attrs['help'] = optparse.SUPPRESS_HELP
            attrs['cli_loadable'] = False
            attrs['env_name'] = ''
            attrs['file_loadable'] = False
            attrs['file_exportable'] = False
        super().__init__(*opts, **attrs)


ALL_DEV_MODE = ['access', 'qweb', 'reload', 'xml']
DEFAULT_SERVER_WIDE_MODULES = ['base', 'rpc', 'web']
REQUIRED_SERVER_WIDE_MODULES = ['base', 'web']


def _no_dups_logs(loggers):
    return ('{}:{}'.format(logger, level) for logger, level
                                          in dict(it.split(':') for it in loggers).items())

class configmanager:
    def __init__(self) -> None:
        self._default_opts: dict[str, str] = {}
        self._file_opts: dict[str, str] = {}
        self._env_opts: dict[str, str] = {}
        self._cli_opts: dict[str, str] = {}
        self._runtime_opts: dict[str, t.Any] = {}
        self.opts = collections.ChainMap(self._runtime_opts,
                                         self._cli_opts,
                                         self._env_opts,
                                         self._file_opts,
                                         self._default_opts,)

        self.opts_index: dict[str, _InphmsOption] = {}
        self.opts_optional: dict[str, _InphmsOption] = {}

        self.parser = self._build_config()
        self._setup_config()
        self._parse_config()

    def _build_config(self) -> optparse.OptionParser:
        InphmsOption = type("InphmsOption", (_InphmsOption,), {"config": self})
        FileOnlyOption = type("FileOnlyOption", (_FileOnlyOption, InphmsOption), {})
        PosixOnlyOption = type("PosixOnlyOption", (_PosixOnlyOption, InphmsOption), {})
    
        version = f"{release.DESCRIPTION} {release.VERSION}"
        parser = optparse.OptionParser(version=version, option_class=InphmsOption)

        # FILE ONLY OPTIONS
        parser.add_option(FileOnlyOption(dest="master_pwd", my_default="admin"))
        parser.add_option(FileOnlyOption(dest='bin_path', type='path', my_default='', file_exportable=False))
        parser.add_option(FileOnlyOption(dest='csv_internal_sep', my_default=','))
        parser.add_option(FileOnlyOption(dest='websocket_keep_alive_timeout', type='int', my_default=3600))
        parser.add_option(FileOnlyOption(dest='websocket_rate_limit_burst', type='int', my_default=10))
        parser.add_option(FileOnlyOption(dest='websocket_rate_limit_delay', type='float', my_default=0.2))

        # COMMON OPTIONS
        group = optparse.OptionGroup(parser, "Common Options")
        group.add_option("-c", '--config',
                         dest="config_file",
                         type="path",
                         file_loadable=False,
                         env_name="INPHMS_RC",
                         help="Load to config file path")
        group.add_option("-s", '--save',
                         dest="save",
                         action="store_true",
                         my_default=False,
                         file_loadable=False,
                         help="Save current config")
        group.add_option("-i", "--init",
                         dest="init",
                         type="comma",
                         metavar="MODULE,...",
                         my_default=[],
                         file_loadable=False,
                         help="install one or more modules (comma-separated list, use \"all\" for all modules), requires -d")
        group.add_option("-u", "--update",
                         dest="update",
                         type="comma",
                         metavar="MODULE,...",
                         my_default=[],
                         file_loadable=False,
                         help="update one or more modules (comma-separated list, use \"all\" for all modules), requires -d")
        group.add_option("--reinit",
                         dest="reinit",
                         type="comma",
                         metavar="MODULE,...",
                         my_default=[],
                         file_loadable=False,
                         help="reinstall one or more modules (comma-separated list, use \"all\" for all modules), requires -d")
        group.add_option("--with-demo",
                         dest="with_demo",
                         action='store_true',
                         my_default=False,
                         help="install demo data in new databases")
        group.add_option("--without-demo",
                         dest="with_demo",
                         type='without_demo',
                         metavar='BOOL',
                         nargs='?',
                         const=True,
                         help="don't install demo data in new databases (default)")
        group.add_option("-P", "--import-partial", 
                         dest="import_partial",
                         type='path',
                         my_default='',
                         file_loadable=False,
                         help="Use this for big data importation, if it crashes you will be able to continue at the current state. Provide a filename to store intermediate importation states.")
        group.add_option("--pidfile",
                         dest="pidfile",
                         type="path",
                         my_default="pid",
                         help="File where the server pid will be stored.")
        group.add_option("--addons-path",
                         dest="addons_path",
                         type='addons_path',
                         metavar='PATH,...',
                         my_default=[],
                         help="specify additional addons paths (separated by commas).")
        group.add_option("--load",
                         dest="server_wide_modules",
                         type="comma",
                         metavar="MODULE,...",
                         my_default=DEFAULT_SERVER_WIDE_MODULES,
                         help="Server wide modules to load (comma-separated list)")
        group.add_option("--upgrade-path",
                         dest="upgrade_path",
                         type='upgrade_path',
                         metavar='PATH,...',
                         my_default=[],
                         help="specify an additional upgrade path.")
        group.add_option("-D", '--data-dir',
                         dest="data_dir",
                         type="path",
                         help="Directory where to store INPHMS data")
        parser.add_option_group(group)

        # SERVER OPTIONS
        group = optparse.OptionGroup(parser, "HTTP Server Options")
        group.add_option("--http-host",
                         dest="http_host",
                         my_default="0.0.0.0",
                         help="Host address to bind to")
        group.add_option("-p", '--http-port',
                         dest="http_port",
                         my_default=8080,
                         type="int",
                         metavar="PORT",
                         help="Port to bind to")
        group.add_option("--no-http",
                         dest="http_enable",
                         action="store_false",
                         my_default=True,
                         help="Disable the HTTP and Longpolling services entirely")
        group.add_option("--limit-memory-soft",
                         dest="limit_memory_soft",
                         my_default=2048 * 1024 * 1024, # 2GB
                         type="int",
                         help="Limit the soft memory usage to this value (in bytes)")
        group.add_option('--limit-time-http',
                         dest="limit_time_http",
                         my_default=120,
                         type="int",
                         help="Limit the time spent on a request (in seconds)")
        group.add_option('--limit-time-cron',
                         dest="limit_time_cron",
                         my_default=-1,
                         type="int",
                         help="Limit the time spent on a cron job (in seconds). "
                              "Set to 0 for no limit. ")
        group.add_option("--x-sendfile",
                         dest="x_sendfile",
                         action="store_true",
                         my_default=False,
                         help="Activate X-Sendfile (apache) and X-Accel-Redirect (nginx) "
                              "HTTP response header to delegate the delivery of large "
                              "files (assets/attachments) to the web server.")
        parser.add_option_group(group)

        # WEB OPTIONS
        group = optparse.OptionGroup(parser, "WEB Interface Options")
        group.add_option("--db-filter",
                         dest="dbfilter",
                         my_default='',
                         metavar="REGEXP",
                         help="Regular expressions for filtering available databases for Web UI. "
                              "The expression can use %d (domain) and %h (host) placeholders.")
        parser.add_option_group(group)

        # TESTIING OPTIONS
        group = optparse.OptionGroup(parser, "Testing Options")
        group.add_option("--test-enable",
                         dest="test_enable",
                         action="store_true",
                         file_loadable=False,
                         help="Enable unit tests. Implies --stop-after-init")
        group.add_option("--test-file",
                         dest="test_file",
                         type='path',
                         my_default='',
                         file_loadable=False,
                         help="Launch a python test file.")
        group.add_option("--test-tags", 
                         dest="test_tags",
                         file_loadable=False,
                         help="Comma-separated list of specs to filter which tests to execute. Enable unit tests if set. "
                         "A filter spec has the format: [-][tag][/module][:class][.method][[params]] "
                         "The '-' specifies if we want to include or exclude tests matching this spec. "
                         "The tag will match tags added on a class with a @tagged decorator "
                         "(all Test classes have 'standard' and 'at_install' tags "
                         "until explicitly removed, see the decorator documentation). "
                         "'*' will match all tags. "
                         "If tag is omitted on include mode, its value is 'standard'. "
                         "If tag is omitted on exclude mode, its value is '*'. "
                         "The module, class, and method will respectively match the module name, test class name and test method name. "
                         "Example: --test-tags :TestClass.test_func,/test_module,external "
                         "It is also possible to provide parameters to a test method that supports them"
                         "Example: --test-tags /web.test_js[mail]"
                         "If negated, a test-tag with parameter will negate the parameter when passing it to the test"

                         "Filtering and executing the tests happens twice: right "
                         "after each module installation/update and at the end "
                         "of the modules loading. At each stage tests are filtered "
                         "by --test-tags specs and additionally by dynamic specs "
                         "'at_install' and 'post_install' correspondingly. Implies --stop-after-init")
        parser.add_option_group(group)

        # DATABASE OPTIONS
        group = optparse.OptionGroup(parser, "Database Related Options")
        group.add_option("--db-list",
                         dest="db_list",
                         type="comma",
                         my_default=[],
                         help="List of Inphms Databases")    
        group.add_option("-r", "--db-user",
                         dest="db_user",
                         my_default="",
                         env_name="PGUSER",
                         help="Postgre Database user name")
        group.add_option("-w", "--db-password",
                         dest="db_password",
                         my_default="",
                         env_name="PGPASSWORD",
                         help="Postgre Database password")
        group.add_option("--pg-path",
                         dest="pg_path",
                         type="path",
                         my_default="",
                         env_name="PGPATH",
                         help="Specify the path to the PostgreSQL client executables.")
        group.add_option("--db-host",
                         dest="db_host",
                         my_default="",
                         env_name="PGHOST",
                         help="Postgre Database host")
        group.add_option("--db-port", 
                         dest="db_port",
                         my_default=None,
                         type="int",
                         env_name="PGPORT",
                         help="Postgre Database port")
        group.add_option("--db-replica-host",
                         dest="db_replica_host",
                         my_default=None,
                         env_name="PGHOST_REPLICA",
                         help="Postgre Replica Database host")
        group.add_option("--db-replica-port",
                         dest="db_replica_port",
                         my_default=None,
                         env_name="PGPORT_REPLICA",
                         type="int",
                         help="Postgre Replica Database port")
        group.add_option("--db-ssl",
                         dest="db_sslmode",
                         type="choice",
                         my_default="prefer",
                         env_name="PGSSLMODE",
                         choices=["allow", "disable", "prefer", "require", "verify-ca", "verify-full"],
                         help="SSL mode to use when connecting to the database")
        group.add_option("--db-appname",
                         dest="db_appname",
                         my_default="inphms-{pid}",
                         env_name="PGAPPNAME",
                         help="Application name to use when connecting to the database, {pid} is replaced by the process id")
        group.add_option("--db-template",
                         dest="db_template",
                         my_default="template0",
                         env_name="PGTEMPLATE",
                         help="Template to use when creating the database")
        group.add_option("--db-maxconn",
                         dest="db_maxconn",
                         type="int",
                         my_default=64,
                         help="Maximum number of connections to the database")
        parser.add_option_group(group)

        # LOGGING OPTIONS
        group = optparse.OptionGroup(parser, "Logging Options")
        group.add_option("--log-handler",
                         action="append",
                         type="comma",
                         my_default=[":INFO"],
                         metavar="MODULE:LEVEL",
                         help="Set a custom logging handler (use comma-separated list of "
                              "module:level, e.g. 'inphms.tools:DEBUG,inphms.netsvc:INFO')")
        group.add_option("--logfile",
                         dest="logfile",
                         type='path',
                         my_default='',
                         help="file where the server log will be stored")
        group.add_option("--syslog",
                         action="store_true",
                         dest="syslog",
                         my_default=False,
                         help="Send the log to the syslog server")
        parser.add_option_group(group)

        # i18n OPTIONS
        group = optparse.OptionGroup(parser, "Internationalization Options")
        group.add_option("--load-language",
                         dest="load_language",
                         file_exportable=False,
                         help="specifies the languages for the translations you want to be loaded")
        group.add_option("--i18n-overwrite",
                         dest="overwrite_existing_translations",
                         action="store_true",
                         my_default=False,
                         file_exportable=False,
                         help="overwrites existing translation terms on updating a module.")
        parser.add_option_group(group)

        # SECURITY OPTIONS
        security = optparse.OptionGroup(parser, "Security Options")
        security.add_option("--no-db-manager",
                             action="store_false",
                             dest="db_manager",
                             my_default=True,
                             help="Disable the database manager")
        parser.add_option_group(security)
        
        # ADVANCE OPTIONS
        group = optparse.OptionGroup(parser, "Advanced Options")
        group.add_option("--dev",
                         dest="dev_mode",
                         type="comma",
                         metavar="FEATURE,...",
                         my_default=[],
                         file_exportable=False,
                         env_name="INPHMS_DEV",
                         help="Enable developer features (comma-separated list, use   "
                              '"all" for access,reload,qweb,xml). Available features: '
                              "- access: log the traceback of access errors           "
                              "- qweb: log the compiled xml with qweb errors          "
                              "- reload: restart server on change in the source code  "
                              "- replica: simulate a deployment with readonly replica "
                              "- werkzeug: open a html debugger on http request error "
                              "- xml: read views from the source code, and not the db ")
        group.add_option("--stop-after-init",
                         action="store_true",
                         dest="stop_after_init",
                         my_default=False,
                         file_exportable=False,
                         file_loadable=False,
                         help="Stop the server after initialization")
        group.add_option("--osv-memory-count-limit",
                         dest="osv_memory_count_limit",
                         my_default=0,
                         help="Force a limit on the maximum number of records kept in the virtual "
                              "osv_memory tables. By default there is no limit.",
                         type="int")
        group.add_option("--transient-age-limit",
                         dest="transient_age_limit",
                         my_default=1.0,
                         help="Time limit (decimal value in hours) records created with a "
                              "TransientModel (mostly wizard) are kept in the database. Default to 1 hour.",
                         type="float")
        group.add_option("--max-cron-threads",
                         dest="max_cron_threads",
                         my_default=2,
                         type="int",
                         help="Maximum number of threads processing concurrently cron jobs (default 2).")
        group.add_option("--limit-time-worker-cron",
                         dest="limit_time_worker_cron",
                         my_default=0,
                         type="int",
                         help="Maximum time a cron thread/worker stays alive before it is restarted. "
                              "Set to 0 to disable. (default: 0)")
        group.add_option("--unaccent",
                         dest="unaccent",
                         my_default=False,
                         action="store_true",
                         help="Try to enable the unaccent extension when creating new databases.")
        group.add_option("--geoip-city-db", "--geoip-db",
                         dest="geoip_city_db",
                         type='path',
                         my_default='/usr/share/GeoIP/GeoLite2-City.mmdb',
                         help="Absolute path to the GeoIP City database file.")
        group.add_option("--geoip-country-db",
                         dest="geoip_country_db",
                         type='path',
                         my_default='/usr/share/GeoIP/GeoLite2-Country.mmdb',
                         help="Absolute path to the GeoIP Country database file.")
        parser.add_option_group(group)

        # Multi processing
        group = optparse.OptionGroup(parser, "Multiprocessing Options")
        group.add_option(PosixOnlyOption(
            "--workers", dest="workers", my_default=0,
            help="Specify the number of workers, 0 disable prefork mode.",
            type="int"
        ))
        group.add_option(PosixOnlyOption(
            "--limit-memory-hard", dest="limit_memory_hard", my_default=2560 * 1024 * 1024,
            help="Maximum allowed virtual memory per workers (in bytes), when reached, any memory allocation will fail (default 2560MiB)"
        ))
        

        return parser

    def _setup_config(self) -> None:
        # default options
        self._default_opts.clear()
        self._default_opts.update({opt_name: opt.my_default
                                   for opt_name, opt in self.opts_index.items()})

        # data dir
        data_dir = f'/var/lib/{release.PRODUCT_NAME}'
        if isdir(expanduser("~")):
            data_dir = appdirs.user_data_dir(release.PRODUCT_NAME, release.AUTHOR)
        elif sys.platform in ['win32', 'darwin']:
            data_dir = appdirs.site_data_dir(release.PRODUCT_NAME, release.AUTHOR)
        self._default_opts['data_dir'] = data_dir

        # config file
        rcfilepath = '~/.inphms.conf'
        if os.name == 'nt':
            rcfilepath = opj(abspath(dirname(self.root_path)), 'inphms.conf')
        elif isfile(rcfilepath:=expanduser("~/.inphms.conf")):
            pass
        self._default_opts['config_file'] = self._normalizepath(rcfilepath)
    
    def _parse_config(self, args:list[str] | None = None) -> optparse.Values:
        # preprocess the args to add support for nargs='?'
        for arg_no, arg in enumerate(args or ()):
            if option := self.opts_optional.get(arg):
                if arg_no == len(args) - 1 or args[arg_no + 1].startswith('-'):
                    args[arg_no] += '=' + self.format(option.dest, option.const)
                    self._log(logging.DEBUG, "changed %s for %s", arg, args[arg_no])

        # unkown args
        opt, unknown = self.parser.parse_args(args or [])
        if unknown:
            self.parser.error(f"Unknown arguments: {', '.join(unknown)}")
        
        # validation
        if not opt.save and opt.config_file and not os.access(opt.config_file, os.R_OK):
            self.parser.error(f"Config file provided {opt.config_file} is not readable")
        
        for option_name in list(vars(opt).keys()):
            if not self.opts_index[option_name].cli_loadable:
                delattr(opt, option_name)
        
        self._load_env_opts()
        self._load_cli_opts(opt)
        self._load_file_opts(self['config_file'])
        self._post_init()
        if opt.save:
            self.save_config()
        return opt

    def _load_env_opts(self) -> None:
        self._env_opts.clear()
        environ = os.environ
        for opt_name, opt in self.opts_index.items():
            env_name = opt.env_name
            if env_name and env_name in environ:
                self._env_opts[opt_name] = self.parse(opt_name, environ[env_name])

    def _load_cli_opts(self, opt:optparse.Values) -> None:
        self._cli_opts.clear()
        keys = [opt_name for opt_name, opt
                in self.opts_index.items()
                if opt.cli_loadable
                if opt.action != 'append']
        for arg in keys:
            if getattr(opt, arg, None) is not None:
                self._cli_opts[arg] = getattr(opt, arg)
        
        if opt.log_handler:
            self._cli_opts['log_handler'] = [handler for comma in opt.log_handler for handler in comma]

    def _load_file_opts(self, filepath:str) -> None:
        self._file_opts.clear()
        p = configparser.RawConfigParser()
        try:
            p.read([filepath])
            for (name, value) in p.items('options'):
                if name == 'without_demo':
                    name = 'with_demo'
                    value = str(self._check_without_demo(None, 'without_demo', value))
                opt = self.opts_index.get(name)
                if not opt:
                    self._file_opts[name] = value
                    continue
                if not opt.file_loadable:
                    continue
                if (
                    value in ('False', 'false')
                    and opt.action not in ('store_true', 'store_false', 'callback')
                    and opt.nargs_ != '?'
                ):
                    # "False" used to be the my_default of many non-bool options
                    self._log(logging.WARNING, "option %s reads %r in the config file at %s but isn't a boolean option, skip", name, value, self['config'])
                    continue
                self._file_opts[name] = self.parse(name, value)
        except IOError:
            pass
        except configparser.NoSectionError:
            pass

    def _post_init(self) -> None:
        self._runtime_opts.clear()
        
        # default server wide modules
        if not self['server_wide_modules']:
            self._runtime_opts['server_wide_modules'] = DEFAULT_SERVER_WIDE_MODULES
        for mod in REQUIRED_SERVER_WIDE_MODULES:
            if mod not in self['server_wide_modules']:
                self._log(logging.INFO, "adding missing %r to %s", mod, self.opts_index['server_wide_modules'])
                self._runtime_opts['server_wide_modules'] = [mod] + self['server_wide_modules']

        # log handler
        self._runtime_opts['log_handler'] = list(_no_dups_logs([*self._default_opts.get('log_handler', []),
                                                                *self._file_opts.get('log_handler', []),
                                                                *self._env_opts.get('log_handler', []),
                                                                *self._cli_opts.get('log_handler', []),
                                                              ]))
    
        self._runtime_opts['init'] = dict.fromkeys(self['init'], True) or {}
        self._runtime_opts['update'] = {'base': True} if 'all' in self['update'] else dict.fromkeys(self['update'], True)
        
        if 'all' in self['dev_mode']:
            self._runtime_opts['dev_mode'] = self['dev_mode'] + ALL_DEV_MODE

        if test_file := self['test_file']:
            if not os.path.isfile(test_file):
                self._log(logging.WARNING, f'test file {test_file!r} cannot be found')
            elif not test_file.endswith('.py'):
                self._log(logging.WARNING, f'test file {test_file!r} is not a python file')
            else:
                self._log(logging.INFO, 'Transforming --test-file into --test-tags')
                test_tags = (self['test_tags'] or '').split(',')
                test_tags.append(os.path.abspath(self['test_file']))
                self._runtime_opts['test_tags'] = ','.join(test_tags)
                self._runtime_opts['test_enable'] = True
        if self['test_enable'] and not self['test_tags']:
            self._runtime_opts['test_tags'] = "+standard"
        self._runtime_opts['test_enable'] = bool(self['test_tags'])
        if self._runtime_opts['test_enable']:
            self._runtime_opts['stop_after_init'] = True
            if not self['db_list']:
                self._log(logging.WARNING,
                    "Empty %s, tests won't run", self.opts_index['db_list'])

    def parse_config(self, args:list[str]) -> optparse.Values:
        opt = self._parse_config(args)

        # setup logger
        from inphms import netsvc, modules
        netsvc.setup_logger()
        self._flush_log()
        modules.module.setup_sys_path()
        return opt

    
    def save_config(self, keys:str|None=None) -> None:
        p = configparser.RawConfigParser()
        is_exists = os.path.exists(self['config_file'])
        if is_exists and keys:
            p.read([self['config_file']])
        if not p.has_section("options"):
            p.add_section("options")
        for opt in sorted(self.opts):
            option = self.opts_index.get(opt)
            if keys is not None and opt not in keys:
                continue
            if opt == 'version' or (option and not option.file_exportable):
                continue
            if option:
                p.set("options", opt, self.format(opt, self.opts[opt]))
            else:
                p.set("options", opt, self.opts[opt])
        
        try:
            if not is_exists and not os.path.exists(dirname(self['config_file'])):
                os.makedirs(dirname(self['config_file']))
            try:
                with open(self['config_file'], 'w', encoding='utf-8') as f:
                    p.write(f)
                if not is_exists:
                    os.chmod(self['config_file'], 0o600)
            except IOError:
                sys.stderr.write("ERROR: could not write to config file %s\n" % self['config_file'])
        except OSError:
            sys.stderr.write("ERROR: could not create config directory %s\n" % dirname(self['config_file']))


    # region: MAPPING

    def __getitem__(self, key) -> t.Any:
        return self.opts[key]

    def __setitem__(self, key: str, value: t.Any) -> t.Any:
        if isinstance(value, str) and key in self.opts_index:
            value = self.parse(key, value)
        self.opts[key] = value
    
    # endregion

    # region: QGET\PROPERTIES

    @functools.cached_property
    def root_path(self):
        return self._normalizepath(opj(dirname(__file__), '.'))

    def get(self, key:str, default=None):
        return self.opts.get(key, default)
    
    @property
    def addons_global_dir(self) -> str:
        return opj(dirname(self.root_path), 'addons')

    @property
    def addons_base_dir(self) -> str:
        return opj(self.root_path, 'addons')
    
    @property
    def session_dir(self) -> str:
        sd = opj(self['data_dir'], 'sessions')
        try:
            os.makedirs(sd, 0o700)
        except OSError as err:
            if err.errno != errno.EEXIST:
                raise
            assert os.access(sd, os.W_OK), \
                f"Cannot write in {sd} directory, please check the permissions"
        return sd
    
    def filestore(self, dbname:str) -> str:
        return opj(self['data_dir'], 'filestore', dbname)

    # endregion

    # region: HELPERS
    @classmethod
    def _normalizepath(cls, path:str) -> str:
        if not path:
            return ''
        return normcase(realpath(abspath(expanduser(expandvars(path.strip())))))

    def set_master_password(self, password:str) -> None:
        self.opts['master_pwd'] = ctx.hash(password)

    def validate_master_password(self, password:str) -> bool:
        stored = self.opts['master_pwd']
        if not stored:
            return False # empty pw/hash => auth forbidden
        res, updated = ctx.verify_and_update(password, stored)
        if res:
            if updated:
                self.opts['master_pwd'] = updated
            return True
        return False

    _log_entries = []

    @classmethod
    def _log(cls, loglevel, message, *args, **kwargs):
        # is replaced by logger.log once logging is ready
        cls._log_entries.append((loglevel, message, args, kwargs))

    @classmethod
    def _flush_log(cls) -> None:
        for loglevel, message, args, kwargs in cls._log_entries:
            _dangerous_logger.log(loglevel, message, *args, **kwargs)
        cls._log_entries.clear()
        cls._log = _dangerous_logger.log

    # endregion

    # region: CHECKER
    
    @classmethod
    def _is_addons_path(cls, path):
        for f in os.listdir(path):
            modpath = os.path.join(path, f)

            def hasfile(filename):
                return os.path.isfile(os.path.join(modpath, filename))
            if hasfile('__init__.py') and hasfile('__manifest__.py'):
                return True
        return False

    @classmethod
    def _check_addons_path(cls, option, opt, value):
        ad_paths = []
        for path in map(cls._normalizepath, cls._check_comma(option, opt, value)):
            if not os.path.isdir(path):
                cls._log(logging.WARNING, "option %s, no such directory %r, skipped", opt, path)
                continue
            if not cls._is_addons_path(path):
                cls._log(logging.WARNING, "option %s, invalid addons directory %r, skipped", opt, path)
                continue
            ad_paths.append(path)

        return ad_paths

    @classmethod
    def _check_upgrade_path(cls, option, opt, value):
        upgrade_path = []
        for path in map(cls._normalizepath, cls._check_comma(option, opt, value)):
            if not os.path.isdir(path):
                cls._log(logging.WARNING, "option %s, no such directory %r, skipped", opt, path)
                continue
            if not cls._is_upgrades_path(path):
                cls._log(logging.WARNING, "option %s, invalid upgrade directory %r, skipped", opt, path)
                continue
            if path not in upgrade_path:
                upgrade_path.append(path)
        return upgrade_path

    @classmethod
    def _check_scripts(cls, option, opt, value):
        pre_upgrade_scripts = []
        for path in map(cls._normalizepath, cls._check_comma(option, opt, value)):
            if not os.path.isfile(path):
                cls._log(logging.WARNING, "option %s, no such file %r, skipped", opt, path)
                continue
            if path not in pre_upgrade_scripts:
                pre_upgrade_scripts.append(path)
        return pre_upgrade_scripts

    @classmethod
    def _is_upgrades_path(cls, path):
        module = '*'
        version = '*'
        return any(
            glob.glob(os.path.join(path, f'{module}/{version}/{prefix}-*.py'))
            for prefix in ['pre', 'post', 'end']
        )

    @classmethod
    def _check_bool(cls, option, opt, value):
        if value.lower() in ('1', 'yes', 'true', 'on'):
            return True
        if value.lower() in ('0', 'no', 'false', 'off'):
            return False
        raise optparse.OptionValueError(
            f"option {opt}: invalid boolean value: {value!r}"
        )

    @classmethod
    def _check_comma(cls, option_name, option, value):
        return [v for s in value.split(',') if (v := s.strip())]

    @classmethod
    def _check_path(cls, option, opt, value):
        return cls._normalizepath(value)

    @classmethod
    def _check_without_demo(cls, option, opt, value):
        # invert the result because it is stored in "with_demo"
        return not cls._check_bool(option, opt, value)

    # endregion

    # region: FORMATTER
    
    @classmethod
    def _format_string(cls, value):
        return str(value)

    @classmethod
    def _format_list(cls, value):
        return ','.join(filter(bool, (str(elem).strip() for elem in value)))

    @classmethod
    def _format_without_demo(cls, value):
        return str(bool(value))

    # endregion

    # region: PARSING HELPERS
    def format(self, opt_name:str, value) -> str:
        opt = self.opts_index[opt_name]
        if opt.action in ('store_true', 'store_false'):
            do_format = self.parser.option_class.TYPE_FORMATTER['bool']
        else:
            do_format = self.parser.option_class.TYPE_FORMATTER[opt.type]
        return do_format(value)

    def parse(self, opt_name:str, value: str) -> str:
        if not isinstance(value, str):
            e = "Can only parse string values for option %s, got %s" % (opt_name, type(value))
            raise TypeError(e)
        if value == 'None':
            return None
        opt = self.opts_index[opt_name]
        if opt.action in ('store_true', 'store_false'):
            do_check = self._check_bool
        else:
            do_check = self.parser.option_class.TYPE_CHECKER[opt.type]
        return do_check(opt, opt_name, value)

config = configmanager()