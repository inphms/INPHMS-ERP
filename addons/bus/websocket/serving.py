from __future__ import annotations
import functools
import json
import threading
import psycopg2
import hashlib
import base64
import os

from psycopg2.pool import PoolError
from urllib.parse import urlparse
from contextlib import closing
from werkzeug.datastructures import ImmutableMultiDict, MultiDict
from werkzeug.exceptions import ServiceUnavailable, HTTPException, BadRequest

from .exception import InvalidWebsocketRequest, InvalidDatabaseException, UpgradeRequired
from .utils import acquire_cursor, _logger, CloseCode, _wsrequest_stack
from .ws import Websocket
from inphms.modules import current_test, Registry
from inphms.service import model as service_model
from inphms.exceptions import SessionExpiredException
from inphms.server.http import root
from inphms.server.request import Request
from inphms.server import Response
from inphms.server.utils import get_default_session
from inphms.config import config

_all__ = ["WebsocketRequest", "WebsocketConnectionHandler"]


class WebsocketRequest:
    def __init__(self, db, httprequest, websocket):
        self.db = db
        self.httprequest = httprequest
        self.session = None
        self.ws = websocket

    def __enter__(self):
        _wsrequest_stack.push(self)
        return self

    def __exit__(self, *args):
        _wsrequest_stack.pop()

    def serve_websocket_message(self, message):
        try:
            jsonrequest = json.loads(message)
            event_name = jsonrequest['event_name']  # mandatory
        except KeyError as exc:
            raise InvalidWebsocketRequest(
                f'Key {exc.args[0]!r} is missing from request'
            ) from exc
        except ValueError as exc:
            raise InvalidWebsocketRequest(
                f'Invalid JSON data, {exc.args[0]}'
            ) from exc
        data = jsonrequest.get('data')
        self.session = self._get_session()

        try:
            self.registry = Registry(self.db)
            threading.current_thread().dbname = self.registry.db_name
            self.registry.check_signaling()
        except (
            AttributeError, psycopg2.OperationalError, psycopg2.ProgrammingError
        ) as exc:
            raise InvalidDatabaseException() from exc

        with closing(acquire_cursor(self.db)) as cr:
            self.env = self.ws.new_env(cr, self.session, set_lang=True)
            service_model.retrying(
                functools.partial(self._serve_ir_websocket, event_name, data),
                self.env,
            )

    def _serve_ir_websocket(self, event_name, data):
        """Process websocket events, in particular authenticate and subscribe, and delegate extra
        processing to the ir.websocket model which is extensible by applications."""
        self.env["ir.websocket"]._authenticate()
        if event_name == "subscribe":
            self.env["ir.websocket"]._subscribe(data)
        self.env["ir.websocket"]._serve_ir_websocket(event_name, data)

    def _get_session(self):
        session = root.session_store.get(self.ws._session.sid)
        if 'next_sid' in session:
            self.ws._session = root.session_store.get(session['next_sid'])
            return self._get_session()
        if not session:
            raise SessionExpiredException()
        return session

    def update_env(self, user=None, context=None, su=None):
        """
        Update the environment of the current websocket request.
        """
        Request.update_env(self, user, context, su)

    def update_context(self, **overrides):
        """
        Override the environment context of the current request with the
        values of ``overrides``. To replace the entire context, please
        use :meth:`~update_env` instead.
        """
        self.update_env(context=dict(self.env.context, **overrides))

    @functools.cached_property
    def cookies(self):
        cookies = MultiDict(self.httprequest.cookies)
        if self.registry:
            self.registry['ir.http']._sanitize_cookies(cookies)
        return ImmutableMultiDict(cookies)


class WebsocketConnectionHandler:
    SUPPORTED_VERSIONS = {'13'}
    # Given by the RFC in order to generate Sec-WebSocket-Accept from
    # Sec-WebSocket-Key value.
    _HANDSHAKE_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    _REQUIRED_HANDSHAKE_HEADERS = {
        'connection', 'host', 'sec-websocket-key',
        'sec-websocket-version', 'upgrade', 'origin',
    }
    # Latest version of the websocket worker. This version should be incremented
    # every time `websocket_worker.js` is modified to force the browser to fetch
    # the new worker bundle.
    _VERSION = "saas-18.5-1"

    @classmethod
    def websocket_allowed(cls, request):
        # WebSockets are disabled during tests because the test environment and
        # the WebSocket thread use the same cursor, leading to race conditions.
        # However, they are enabled during tours as RPC requests and WebSocket
        # instances both use the `TestCursor` class wich is locked.
        # See `HttpCase@browser_js`.
        return not current_test

    @classmethod
    def open_connection(cls, request, version):
        """
        Open a websocket connection if the handshake is successfull.
        :return: Response indicating the server performed a connection
        upgrade.
        :raise: UpgradeRequired if there is no intersection between the
        versions the client supports and those we support.
        :raise: BadRequest if the handshake data is incorrect.
        """
        if not cls.websocket_allowed(request):
            raise ServiceUnavailable("Websocket is disabled in test mode")
        public_session = cls._handle_public_configuration(request)
        try:
            response = cls._get_handshake_response(request.httprequest.headers)
            socket = request.httprequest._HTTPRequest__environ['socket']
            session, db, httprequest = (public_session or request.session), request.db, request.httprequest
            response.call_on_close(lambda: cls._serve_forever(
                Websocket(socket, session, httprequest.cookies),
                db,
                httprequest,
                version
            ))
            # Force save the session. Session must be persisted to handle
            # WebSocket authentication.
            request.session.is_dirty = True
            return response
        except KeyError as exc:
            raise RuntimeError(
                f"Couldn't bind the websocket. Is the connection opened on the evented port ({config['gevent_port']})?"
            ) from exc
        except HTTPException as exc:
            # The HTTP stack does not log exceptions derivated from the
            # HTTPException class since they are valid responses.
            _logger.error(exc)
            raise


    @classmethod
    def _get_handshake_response(cls, headers):
        """
        :return: Response indicating the server performed a connection
        upgrade.
        :raise: BadRequest
        :raise: UpgradeRequired
        """
        cls._assert_handshake_validity(headers)
        # sha-1 is used as it is required by
        # https://datatracker.ietf.org/doc/html/rfc6455#page-7
        accept_header = hashlib.sha1(
            (headers['sec-websocket-key'] + cls._HANDSHAKE_GUID).encode()).digest()
        accept_header = base64.b64encode(accept_header)
        return Response(status=101, headers={
            'Upgrade': 'websocket',
            'Connection': 'Upgrade',
            'Sec-WebSocket-Accept': accept_header.decode(),
        })

    @classmethod
    def _handle_public_configuration(cls, request):
        if not os.getenv('INPHMS_BUS_PUBLIC_SAMESITE_WS'):
            return
        headers = request.httprequest.headers
        origin_url = urlparse(headers.get('origin'))
        if origin_url.netloc != headers.get('host') or origin_url.scheme != request.httprequest.scheme:
            _logger.warning(
                'Downgrading websocket session. Host=%(host)s, Origin=%(origin)s, Scheme=%(scheme)s.',
                {
                    'host': headers.get('host'),
                    'origin': headers.get('origin'),
                    'scheme': request.httprequest.scheme,
                },
            )
            session = root.session_store.new()
            session.update(get_default_session(), db=request.session.db)
            root.session_store.save(session)
            return session
        return None

    @classmethod
    def _assert_handshake_validity(cls, headers):
        """
        :raise: UpgradeRequired if there is no intersection between
        the version the client supports and those we support.
        :raise: BadRequest in case of invalid handshake.
        """
        missing_or_empty_headers = {
            header for header in cls._REQUIRED_HANDSHAKE_HEADERS
            if header not in headers
        }
        if missing_or_empty_headers:
            raise BadRequest(
                f"""Empty or missing header(s): {', '.join(missing_or_empty_headers)}"""
            )

        if headers['upgrade'].lower() != 'websocket':
            raise BadRequest('Invalid upgrade header')
        if 'upgrade' not in headers['connection'].lower():
            raise BadRequest('Invalid connection header')
        if headers['sec-websocket-version'] not in cls.SUPPORTED_VERSIONS:
            raise UpgradeRequired()

        key = headers['sec-websocket-key']
        try:
            decoded_key = base64.b64decode(key, validate=True)
        except ValueError:
            raise BadRequest("Sec-WebSocket-Key should be b64 encoded")
        if len(decoded_key) != 16:
            raise BadRequest(
                "Sec-WebSocket-Key should be of length 16 once decoded"
            )

    @classmethod
    def _serve_forever(cls, websocket, db, httprequest, version):
        """
        Process incoming messages and dispatch them to the application.
        """
        current_thread = threading.current_thread()
        current_thread.type = 'websocket'
        if httprequest.user_agent and version != cls._VERSION:
            # Close the connection from an outdated worker. We can't use a
            # custom close code because the connection is considered successful,
            # preventing exponential reconnect backoff. This would cause old
            # workers to reconnect frequently, putting pressure on the server.
            # Clean closes don't trigger reconnections, assuming they are
            # intentional. The reason indicates to the origin worker not to
            # reconnect, preventing old workers from lingering after updates.
            # Non browsers are ignored since IOT devices do not provide the
            # worker version.
            websocket.close(CloseCode.CLEAN, "OUTDATED_VERSION")
        for message in websocket.get_messages():
            with WebsocketRequest(db, httprequest, websocket) as req:
                try:
                    req.serve_websocket_message(message)
                except SessionExpiredException:
                    websocket.close(CloseCode.SESSION_EXPIRED)
                except PoolError:
                    websocket.close(CloseCode.TRY_LATER)
                except Exception:
                    _logger.exception("Exception occurred during websocket request handling")
