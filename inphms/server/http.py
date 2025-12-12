from __future__ import annotations
import threading
import time
import logging
import functools
import geoip2
import geoip2.database
import maxminddb
import werkzeug
import werkzeug.routing
import inphms.service.db
import inphms.service.common
import inphms.service.model

try:
    from werkzeug.urls import url_encode, url_quote # type: ignore
except:
    import urllib.parse
    url_encode = urllib.parse.urlencode
    url_quote = urllib.parse.quote
from werkzeug.exceptions import HTTPException
from os.path import join as opj
from urllib.parse import urlparse

from .fs import FilesystemSessionStore, Session
from .utils import request, _request_stack
from .request import Request
from .dispatchers import HttpDispatcher
from .routing import _generate_routing_rules, ROUTING_KEYS
from .utils import thread_local, borrow_request
from inphms.modules import Manifest
from inphms.tools import file_path, submap
from inphms.config import config
from inphms.exceptions import RegistryError, SessionExpiredException, AccessError, UserError, AccessDenied


_logger = logging.getLogger("inphms.server.http")


class Application:
    def static_path(self, module_name: str) -> str | None:
        """ Map module names to their absolute ``static`` path on the file
            system.
        """
        manifest = Manifest.for_addon(module_name, display_warning=False)
        return manifest.static_path if manifest is not None else None

    def get_static_file(self, url, host=''):
        """ Get the full-path of the file if the url resolves to a local
            static file, otherwise return None.
        """

        netloc, path = urlparse(url)[1:3]
        try:
            path_netloc, module, static, resource = path.split('/', 3)
        except ValueError:
            return None

        if ((netloc and netloc != host) or (path_netloc and path_netloc != host)):
            return None

        if not (static == 'static' and resource):
            return None

        static_path = self.static_path(module)
        if not static_path:
            return None

        try:
            return file_path(opj(static_path, resource))
        except FileNotFoundError:
            return None

    @functools.cached_property
    def nodb_routing_map(self):
        nodb_routing_map = werkzeug.routing.Map(strict_slashes=False, converters=None)
        for url, endpoint in _generate_routing_rules([''] + config['server_wide_modules'], nodb_only=True):
            routing = submap(endpoint.routing, ROUTING_KEYS)
            if routing['methods'] is not None and 'OPTIONS' not in routing['methods']:
                routing['methods'] = [*routing['methods'], 'OPTIONS']
            rule = werkzeug.routing.Rule(url, endpoint=endpoint, **routing)
            rule.merge_slashes = False
            nodb_routing_map.add(rule)

        return nodb_routing_map

    @functools.cached_property
    def session_store(self):
        path = config.session_dir
        _logger.debug('HTTP sessions stored in: %s', path)
        return FilesystemSessionStore(path, session_class=Session, renew_missing=True)

    def get_db_router(self, db):
        if not db:
            return self.nodb_routing_map
        return request.env['ir.http'].routing_map()

    @functools.cached_property
    def geoip_city_db(self):
        try:
            return geoip2.database.Reader(config['geoip_city_db'])
        except (OSError, maxminddb.InvalidDatabaseError):
            _logger.debug(
                "Couldn't load Geoip City file at %s. IP Resolver disabled.",
                config['geoip_city_db'], exc_info=True
            )
            raise

    @functools.cached_property
    def geoip_country_db(self):
        try:
            return geoip2.database.Reader(config['geoip_country_db'])
        except (OSError, maxminddb.InvalidDatabaseError) as exc:
            _logger.debug("Couldn't load Geoip Country file (%s). Fallbacks on Geoip City.", exc,)
            raise

    def set_csp(self, response):
        headers = response.headers
        headers['X-Content-Type-Options'] = 'nosniff'

        if 'Content-Security-Policy' in headers:
            return

        if not headers.get('Content-Type', '').startswith('image/'):
            return

        headers['Content-Security-Policy'] = "default-src 'none'"

    def __call__(self, environ, start_response):
        """ WSGI application entry point. """
        current_thread = threading.current_thread()
        current_thread.query_count = 0
        current_thread.query_time = 0
        current_thread.performance_t0 = time.time()
        current_thread.cursor_mode = None
        if hasattr(current_thread, 'dbname'):
            del current_thread.dbname
        if hasattr(current_thread, 'uid'):
            del current_thread.uid
        thread_local.rpc_model_method = ''

        from . import HTTPRequest
        with HTTPRequest(environ) as httprequest:
            request = Request(httprequest)
            _request_stack.push(request)

            try:
                request._post_init()
                current_thread.url = httprequest.url

                if self.get_static_file(httprequest.path):
                    response = request._serve_static()
                elif request.db:
                    try:
                        with request._get_profiler_context_manager():
                            response = request._serve_db()
                    except RegistryError as e:
                        _logger.warning("Database or registry unusable, trying without", exc_info=e.__cause__)
                        request.db = None
                        request.session.logout()
                        if (httprequest.path.startswith('/inphms/')
                            or httprequest.path in (
                                '/inphms', '/web', '/web/login', '/test_http/ensure_db',
                            )):
                            # ensure_db() protected routes, remove ?db= from the query string
                            args_nodb = request.httprequest.args.copy()
                            args_nodb.pop('db', None)
                            request.reroute(httprequest.path, url_encode(args_nodb))
                        response = request._serve_nodb()
                else:
                    response = request._serve_nodb()
                return response(environ, start_response)

            except Exception as exc:
                # Valid (2xx/3xx) response returned via werkzeug.exceptions.abort.
                if isinstance(exc, HTTPException) and exc.code is None:
                    response = exc.get_response()
                    HttpDispatcher(request).post_dispatch(response)
                    return response(environ, start_response)

                # Logs the error here so the traceback starts with ``__call__``.
                if hasattr(exc, 'loglevel'):
                    _logger.log(exc.loglevel, exc, exc_info=getattr(exc, 'exc_info', None))
                elif isinstance(exc, HTTPException):
                    pass
                elif isinstance(exc, SessionExpiredException):
                    _logger.info(exc)
                elif isinstance(exc, AccessError):
                    _logger.warning(exc, exc_info='access' in config['dev_mode'])
                elif isinstance(exc, UserError):
                    _logger.warning(exc)
                else:
                    _logger.exception("Exception during request handling.")

                # Ensure there is always a WSGI handler attached to the exception.
                if not hasattr(exc, 'error_response'):
                    if isinstance(exc, AccessDenied):
                        exc.suppress_traceback()
                    exc.error_response = request.dispatcher.handle_error(exc)

                return exc.error_response(environ, start_response)

            finally:
                _request_stack.pop()


root = Application()


#########
# HELPERS
#########
def content_disposition(filename, disposition_type='attachment'):
    """ Craft a ``Content-Disposition`` header, see :rfc:`6266`.

        :param filename: The name of the file, should that file be saved on
            disk by the browser.
        :param disposition_type: Tell the browser what to do with the file,
            either ``"attachment"`` to save the file on disk,
            either ``"inline"`` to display the file.
    """
    if disposition_type not in ('attachment', 'inline'):
        e = f"Invalid disposition_type: {disposition_type!r}"
        raise ValueError(e)
    return "{}; filename*=UTF-8''{}".format(
        disposition_type,
        url_quote(filename, safe='', unsafe='()<>@,;:"/[]?={}\\*\'%') # RFC6266
    )


def dispatch_rpc(service_name, method, params):
    """ Perform a RPC call.

        :param str service_name: either "common", "db" or "object".
        :param str method: the method name of the given service to execute
        :param Mapping params: the keyword arguments for method call
        :return: the return value of the called method
        :rtype: Any
    """
    rpc_dispatchers = {
        'common': inphms.service.common.dispatch,
        'db': inphms.service.db.dispatch,
        'object': inphms.service.model.dispatch,
    }

    with borrow_request():
        threading.current_thread().uid = None
        threading.current_thread().dbname = None

        dispatch = rpc_dispatchers[service_name]
        return dispatch(method, params)