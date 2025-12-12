from __future__ import annotations
import werkzeug
import werkzeug.exceptions
import logging
import threading
import functools
import hashlib
import hmac
import time
import json
import contextlib
import psycopg2
import babel.core

from werkzeug.exceptions import NotFound, HTTPException, UnsupportedMediaType
from werkzeug.urls import URL, url_parse, url_encode
import werkzeug.utils
import werkzeug.datastructures
import werkzeug.security

from .geoip import GeoIP
from .response import Response
from .futureresponse import FutureResponse
from .dispatchers import _dispatchers, JsonRPCDispatcher
from .httprequest import HTTPRequest
from .streaming import Stream
from .utils import \
    get_default_session, CSRF_TOKEN_SALT, STORED_SESSION_BYTES, \
    request, get_session_max_inactivity, SESSION_ROTATION_INTERVAL, \
    is_cors_preflight, STATIC_CACHE, NOT_FOUND_NODB, db_filter, db_list, \
    DEFAULT_LANG
from inphms.modules import Registry, Environment
from inphms.tools import json_default
from inphms.exceptions import RegistryError, AccessDenied
from inphms.config import config
from inphms.service import model as service_model


_logger = logging.getLogger("inphms.server.http")

consteq = hmac.compare_digest

class Request:
    """ Wrapper around the incoming HTTP request with deserialized request
        parameters, session utilities and request dispatching logic.
    """

    def __init__(self, httprequest):
        self.httprequest = httprequest
        self.future_response = FutureResponse()
        self.dispatcher = _dispatchers['http'](self)

        self.geoip = GeoIP(httprequest.remote_addr)
        self.registry = None
        self.env = None

    def _post_init(self):
        self.session, self.db = self._get_session_and_dbname()
        self._post_init = None

    def _get_session_and_dbname(self):
        from . import root
        sid = self.httprequest._session_id__
        if not sid or not root.session_store.is_valid_key(sid):
            session = root.session_store.new()
        else:
            session = root.session_store.get(sid)
            session.sid = sid  # in case the session was not persisted

        for key, val in get_default_session().items():
            session.setdefault(key, val)
        if not session.context.get('lang'):
            session.context['lang'] = self.default_lang()

        dbname = None
        host = self.httprequest.environ['HTTP_HOST']
        header_dbname = self.httprequest.headers.get('X-Inphms-Database')
        if session.db and db_filter([session.db], host=host):
            dbname = session.db
            if header_dbname and header_dbname != dbname:
                e = ("Cannot use both the session_id cookie and the "
                     "x-inphms-database header.")
                raise werkzeug.exceptions.Forbidden(e)
        elif header_dbname:
            session.can_save = False  # stateless
            if db_filter([header_dbname], host=host):
                dbname = header_dbname
        else:
            all_dbs = db_list(force=True, host=host)
            if len(all_dbs) == 1:
                dbname = all_dbs[0]  # monodb

        if session.db != dbname:
            if session.db:
                _logger.warning("Logged into database %r, but dbfilter rejects it; logging session out.", session.db)
                session.logout(keep_db=False)
            session.db = dbname

        session.is_dirty = False
        return session, dbname

    # =====================================================
    # Getters and setters
    # =====================================================
    def update_env(self, user=None, context=None, su=None):
        """ Update the environment of the current request. """
        cr = None  # None is a sentinel, it keeps the same cursor
        self.env = self.env(cr, user, context, su)
        self.env.transaction.default_env = self.env
        threading.current_thread().uid = self.env.uid

    def update_context(self, **overrides):
        """ Update the context of the current request."""
        self.update_env(context=dict(self.env.context, **overrides))


    @functools.cached_property
    def best_lang(self):
        lang = self.httprequest.accept_languages.best
        if not lang:
            return None

        try:
            code, territory, _, _ = babel.core.parse_locale(lang, sep='-')
            if territory:
                lang = f'{code}_{territory}'
            else:
                lang = babel.core.LOCALE_ALIASES[code]
            return lang
        except (ValueError, KeyError):
            return None

    @functools.cached_property
    def cookies(self):
        cookies = werkzeug.datastructures.MultiDict(self.httprequest.cookies)
        if self.registry:
            self.registry['ir.http']._sanitize_cookies(cookies)
        return werkzeug.datastructures.ImmutableMultiDict(cookies)

    # =====================================================
    # Helpers
    # =====================================================
    def csrf_token(self, time_limit=None):
        """ Generates and returns a CSRF token for the current session. """
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        if not secret:
            raise ValueError("CSRF protection requires a configured database secret")

        # if no `time_limit` => distant 1y expiry so max_ts acts as salt, e.g. vs BREACH
        max_ts = int(time.time() + (time_limit or CSRF_TOKEN_SALT))
        msg = f'{self.session.sid[:STORED_SESSION_BYTES]}{max_ts}'.encode()

        hm = hmac.new(secret.encode('ascii'), msg, hashlib.sha1).hexdigest()
        return f'{hm}o{max_ts}'

    def validate_csrf(self, csrf):
        """ Is the given csrf token valid ? """
        if not csrf:
            return False

        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        if not secret:
            raise ValueError("CSRF protection requires a configured database secret")

        hm, _, max_ts = csrf.rpartition('o')
        msg = f'{self.session.sid[:STORED_SESSION_BYTES]}{max_ts}'.encode()

        if max_ts:
            try:
                if int(max_ts) < int(time.time()):
                    return False
            except ValueError:
                return False

        hm_expected = hmac.new(secret.encode('ascii'), msg, hashlib.sha1).hexdigest()
        return consteq(hm, hm_expected)

    def default_context(self):
        return dict(get_default_session()['context'])

    def default_lang(self):
        """Returns default user language according to request specification

        :returns: Preferred language if specified or 'en_US'
        :rtype: str
        """
        return self.best_lang or DEFAULT_LANG

    def get_http_params(self):
        params = {**self.httprequest.args,
                  **self.httprequest.form,
                  **self.httprequest.files}
        return params

    def get_json_data(self):
        return json.loads(self.httprequest.get_data(as_text=True))

    def _get_profiler_context_manager(self):
        """ Get a profiler when the profiling is enabled and the requested
            URL is profile-safe. Otherwise, get a context-manager that does
            nothing.
        """
        
        return contextlib.nullcontext()

    def _inject_future_response(self, response):
        response.headers.extend(self.future_response.headers)
        return response

    def make_response(self, data, headers=None, cookies=None, status=200):
        """ Helper for non-HTML responses, or HTML responses with custom
            response headers or cookies.
        """
        response = Response(data, status=status, headers=headers)
        if cookies:
            for k, v in cookies.items():
                response.set_cookie(k, v)
        return response

    def make_json_response(self, data, headers=None, cookies=None, status=200):
        """ Helper for JSON responses, it json-serializes ``data`` and
            sets the Content-Type header accordingly if none is provided.
        """
        data = json.dumps(data, ensure_ascii=False, default=json_default)

        headers = werkzeug.datastructures.Headers(headers)
        headers['Content-Length'] = len(data)
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json; charset=utf-8'

        return self.make_response(data, headers.to_wsgi_list(), cookies, status)

    def not_found(self, description=None):
        """ Shortcut for a `HTTP 404
            <http://tools.ietf.org/html/rfc7231#section-6.5.4>`_ (Not Found)
            response
        """
        return NotFound(description)

    def redirect(self, location, code=303, local=True):
        # compatibility, Werkzeug support URL as location
        if isinstance(location, URL):
            location = location.to_url()
        if local:
            location = '/' + url_parse(location).replace(scheme='', netloc='').to_url().lstrip('/\\')
        if self.db:
            return self.env['ir.http']._redirect(location, code)
        return werkzeug.utils.redirect(location, code, Response=Response)

    def redirect_query(self, location, query=None, code=303, local=True):
        if query:
            location += '?' + url_encode(query)
        return self.redirect(location, code=code, local=local)

    def render(self, template, qcontext=None, lazy=True, **kw):
        """ Lazy render of a QWeb template. """
        response = Response(template=template, qcontext=qcontext, **kw)
        if not lazy:
            return response.render()
        return response

    def reroute(self, path, query_string=None):
        """ Rewrite the current request URL using the new path and query
            string. This act as a light redirection, it does not return a
            3xx responses to the browser but still change the current URL.
        """
        # WSGI encoding dance https://peps.python.org/pep-3333/#unicode-issues
        if isinstance(path, str):
            path = path.encode('utf-8')
        path = path.decode('latin1', 'replace')

        if query_string is None:
            query_string = request.httprequest.environ['QUERY_STRING']

        # Change the WSGI environment
        environ = self.httprequest._HTTPRequest__environ.copy()
        environ['PATH_INFO'] = path
        environ['QUERY_STRING'] = query_string
        environ['RAW_URI'] = f'{path}?{query_string}'
        # REQUEST_URI left as-is so it still contains the original URI

        # Create and expose a new request from the modified WSGI env
        httprequest = HTTPRequest(environ)
        threading.current_thread().url = httprequest.url
        self.httprequest = httprequest

    def _save_session(self, env=None):
        """ Save a modified session on disk.

            :param env: an environment to compute the session token.
                MUST be left ``None`` (in which case it uses the request's
                env) UNLESS the database changed.
        """
        from . import root

        sess = self.session
        if env is None:
            env = self.env

        if not sess.can_save:
            return

        if sess.should_rotate:
            root.session_store.rotate(sess, env)  # it saves
        elif sess.uid and time.time() >= sess['create_time'] + SESSION_ROTATION_INTERVAL:
            root.session_store.rotate(sess, env, True)
        elif sess.is_dirty:
            root.session_store.save(sess)

        cookie_sid = self.cookies.get('session_id')
        if sess.is_dirty or cookie_sid != sess.sid:
            self.future_response.set_cookie(
                'session_id',
                sess.sid,
                max_age=get_session_max_inactivity(env),
                httponly=True
            )

    def _set_request_dispatcher(self, rule):
        routing = rule.endpoint.routing
        dispatcher_cls = _dispatchers[routing['type']]
        if (not is_cors_preflight(self, rule.endpoint)
            and not dispatcher_cls.is_compatible_with(self)):
            compatible_dispatchers = [
                disp.routing_type
                for disp in _dispatchers.values()
                if disp.is_compatible_with(self)
            ]
            e = (f"Request inferred type is compatible with {compatible_dispatchers} "
                 f"but {routing['routes'][0]!r} is type={routing['type']!r}.\n\n"
                 "Please verify the Content-Type request header and try again.")
            # werkzeug doesn't let us add headers to UnsupportedMediaType
            # so use the following (ugly) to still achieve what we want
            res = UnsupportedMediaType(e).get_response()
            res.headers['Accept'] = ', '.join(dispatcher_cls.mimetypes)
            raise UnsupportedMediaType(response=res)
        self.dispatcher = dispatcher_cls(self)

    # =====================================================
    # Routing
    # =====================================================
    def _serve_static(self):
        """ Serve a static file from the file system. """
        module, _, path = self.httprequest.path[1:].partition('/static/')
        try:
            from . import root
            directory = root.static_path(module)
            if not directory:
                raise NotFound(f'Module "{module}" not found.\n')
            filepath = werkzeug.security.safe_join(directory, path)
            debug = (
                'assets' in self.session.debug and
                ' wkhtmltopdf ' not in self.httprequest.user_agent.string
            )
            res = Stream.from_path(filepath, public=True).get_response(
                max_age=0 if debug else STATIC_CACHE,
                content_security_policy=None,
            )
            root.set_csp(res)
            return res
        except OSError:  # cover both missing file and invalid permissions
            raise NotFound(f'File "{path}" not found in module {module}.\n')

    def _serve_nodb(self):
        """ Dispatch the request to its matching controller in a
            database-free environment.
        """
        from . import root
        router = root.nodb_routing_map.bind_to_environ(self.httprequest.environ)
        try:
            rule, args = router.match(return_rule=True)
        except NotFound as exc:
            exc.response = Response(NOT_FOUND_NODB, status=exc.code, headers=[
                ('Content-Type', 'text/html; charset=utf-8'),
            ])
            raise
        self._set_request_dispatcher(rule)
        self.dispatcher.pre_dispatch(rule, args)
        response = self.dispatcher.dispatch(rule.endpoint, args)
        self.dispatcher.post_dispatch(response)
        return response

    def _serve_db(self):
        """ Load the ORM and use it to process the request. """
        # reuse the same cursor for building, checking the registry, for
        # matching the controller endpoint and serving the data
        cr = None
        try:
            # get the registry and cursor (RO)
            try:
                registry = Registry(self.db)
                cr = registry.cursor(readonly=True)
                self.registry = registry.check_signaling(cr)
            except (AttributeError, psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
                raise RegistryError(f"Cannot get registry {self.db}") from e
            threading.current_thread().dbname = self.registry.db_name

            # find the controller endpoint to use
            self.env = Environment(cr, self.session.uid, self.session.context)
            try:
                rule, args = self.registry['ir.http']._match(self.httprequest.path)
            except NotFound as not_found_exc:
                # no controller endpoint matched -> fallback or 404
                serve_func = functools.partial(self._serve_ir_http_fallback, not_found_exc)
                readonly = True
            else:
                # a controller endpoint matched -> dispatch it the request
                self._set_request_dispatcher(rule)
                serve_func = functools.partial(self._serve_ir_http, rule, args)
                readonly = rule.endpoint.routing['readonly']
                if callable(readonly):
                    readonly = readonly(rule.endpoint.func.__self__, rule, args)

            # keep on using the RO cursor when a readonly route matched,
            # and for serve fallback
            if readonly and cr.readonly:
                threading.current_thread().cursor_mode = 'ro'
                try:
                    return service_model.retrying(serve_func, env=self.env)
                except psycopg2.errors.ReadOnlySqlTransaction as exc:
                    # although the controller is marked read-only, it
                    # attempted a write operation, try again using a
                    # read/write cursor
                    _logger.warning("%s, retrying with a read/write cursor", exc.args[0].rstrip(), exc_info=True)
                    threading.current_thread().cursor_mode = 'ro->rw'
                except Exception as exc:  # noqa: BLE001
                    raise self._update_served_exception(exc)
            else:
                threading.current_thread().cursor_mode = 'rw'

            # we must use a RW cursor when a read/write route matched, or
            # there was a ReadOnlySqlTransaction error
            if cr.readonly:
                cr.close()
                cr = self.env.registry.cursor()
            else:
                # the cursor is already a RW cursor, start a new transaction
                # that will avoid repeatable read serialization errors because
                # check signaling is not done in `retrying` and that function
                # would just succeed the second time
                cr.rollback()
            assert not cr.readonly
            self.env = self.env(cr=cr)
            try:
                return service_model.retrying(serve_func, env=self.env)
            except Exception as exc:  # noqa: BLE001
                raise self._update_served_exception(exc)
        finally:
            if cr is not None:
                cr.close()

    def _update_served_exception(self, exc):
        if isinstance(exc, HTTPException) and exc.code is None:
            return exc  # bubble up to inphms.http.Application.__call__
        if (
            'werkzeug' in config['dev_mode']
            and self.dispatcher.routing_type != JsonRPCDispatcher.routing_type
        ):
            return exc  # bubble up to werkzeug.debug.DebuggedApplication
        if not hasattr(exc, 'error_response'):
            if isinstance(exc, AccessDenied):
                exc.suppress_traceback()
            exc.error_response = self.registry['ir.http']._handle_error(exc)
        return exc

    def _serve_ir_http_fallback(self, not_found):
        """ Called when no controller match the request path. Delegate to
            ``ir.http._serve_fallback`` to give modules the opportunity to
            find an alternative way to serve the request. In case no module
            provided a response, a generic 404 - Not Found page is returned.
        """
        self.params = self.get_http_params()
        self.registry['ir.http']._auth_method_public()
        response = self.registry['ir.http']._serve_fallback()
        if response:
            self.registry['ir.http']._post_dispatch(response)
            return response

        no_fallback = NotFound()
        no_fallback.__context__ = not_found  # During handling of {not_found}, {no_fallback} occurred:
        no_fallback.error_response = self.registry['ir.http']._handle_error(no_fallback)
        raise no_fallback

    def _serve_ir_http(self, rule, args):
        """ Called when a controller match the request path. Delegate to
            ``ir.http`` to serve a response.
        """
        self.registry['ir.http']._authenticate(rule.endpoint)
        self.registry['ir.http']._pre_dispatch(rule, args)
        response = self.dispatcher.dispatch(rule.endpoint, args)
        self.registry['ir.http']._post_dispatch(response)
        return response
