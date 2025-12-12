from __future__ import annotations
import time
import bisect
import inphms
import selectors
import struct
import json
import socket
import functools

from collections import defaultdict, deque
from contextlib import suppress, closing
from psycopg2.pool import PoolError

from inphms.modules import Environment, Registry
from inphms.config import config
from inphms.service import model as service_model
from inphms.service.security import check_session
from inphms.server.http import root
from inphms.exceptions import SessionExpiredException
from .exception import PayloadTooLargeException, ProtocolError, InvalidStateException, \
    RateLimitExceededException, InvalidCloseCodeException, ConnectionClosed
from .utils import acquire_cursor, _logger, TimeoutManager, PollablePriorityQueue, ConnectionState, LifecycleEvent, _websocket_instances, \
    CloseCode, TimeoutReason, ControlCommand, _XOR_TABLE, Opcode, CTRL_OP, Frame, CloseFrame, CLEAN_CLOSE_CODES, _command_uid
from ..models.bus import dispatch

__all__ = ["Websocket"]


class Websocket:
    __event_callbacks = defaultdict(set)
    # Maximum size for a message in bytes, whether it is sent as one
    # frame or many fragmented ones.
    MESSAGE_MAX_SIZE = 2 ** 20
    # Proxies usually close a connection after 1 minute of inactivity.
    # Therefore, a PING frame have to be sent if no frame is either sent
    # or received within CONNECTION_TIMEOUT - 15 seconds.
    CONNECTION_TIMEOUT = 60
    INACTIVITY_TIMEOUT = CONNECTION_TIMEOUT - 15
    # How much time (in second) the history of last dispatched notifications is
    # kept in memory for each websocket.
    # To avoid duplicate notifications, we fetch them based on their ids.
    # However during parallel transactions, ids are assigned immediately (when
    # they are requested), but the notifications are dispatched at the time of
    # the commit. This means lower id notifications might be dispatched after
    # higher id notifications.
    # Simply incrementing the last id is sufficient to guarantee no duplicates,
    # but it is not sufficient to guarantee all notifications are dispatched,
    # and in particular not sufficient for those with a lower id coming after a
    # higher id was dispatched.
    # To solve the issue of missed notifications, the lowest id, stored in
    # ``_last_notif_sent_id``, is held back by a few seconds to give time for
    # concurrent transactions to finish. To avoid dispatching duplicate
    # notifications, the history of already dispatched notifications during this
    # period is kept in memory in ``_notif_history`` and the corresponding
    # notifications are discarded from subsequent dispatching even if their id
    # is higher than ``_last_notif_sent_id``.
    # In practice, what is important functionally is the time between the create
    # of the notification and the commit of the transaction in business code.
    # If this time exceeds this threshold, the notification will never be
    # dispatched if the target user receive any other notification in the
    # meantime.
    # Transactions known to be long should therefore create their notifications
    # at the end, as close as possible to their commit.
    MAX_NOTIFICATION_HISTORY_SEC = 10
    # How many requests can be made in excess of the given rate.
    RL_BURST = int(config['websocket_rate_limit_burst'])
    # How many seconds between each request.
    RL_DELAY = float(config['websocket_rate_limit_delay'])

    def __init__(self, sock, session, cookies):
        # Session linked to the current websocket connection.
        self._session = session
        # Cookies linked to the current websocket connection.
        self._cookies = cookies
        self._db = session.db
        self.__socket = sock
        self._close_sent = False
        self._close_received = False
        self._timeout_manager = TimeoutManager()
        # Used for rate limiting.
        self._incoming_frame_timestamps = deque(maxlen=self.RL_BURST)
        # Command queue used to manage the websocket instance externally, such
        # as triggering notification dispatching or terminating the connection.
        self.__cmd_queue = PollablePriorityQueue()
        self._waiting_for_dispatch = False
        self._channels = set()
        # For ``_last_notif_sent_id and ``_notif_history``, see
        # ``MAX_NOTIFICATION_HISTORY_SEC`` for more details.
        # id of the last sent notification that is no longer in _notif_history
        self._last_notif_sent_id = 0
        # history of last sent notifications in the format (notif_id, send_time)
        # always sorted by notif_id ASC
        self._notif_history = []
        # Websocket start up
        self.__selector = (
            selectors.PollSelector()
            if inphms.evented and hasattr(selectors, 'PollSelector')
            else selectors.DefaultSelector()
        )
        self.__selector.register(self.__socket, selectors.EVENT_READ)
        self.__selector.register(self.__cmd_queue, selectors.EVENT_READ)
        self.state = ConnectionState.OPEN
        _websocket_instances.add(self)
        self._trigger_lifecycle_event(LifecycleEvent.OPEN)

    # ------------------------------------------------------
    # PUBLIC METHODS
    # ------------------------------------------------------

    def get_messages(self):
        while self.state is not ConnectionState.CLOSED:
            try:
                readables = {
                    selector_key[0].fileobj for selector_key in
                    self.__selector.select(self.INACTIVITY_TIMEOUT)
                }
                if self._timeout_manager.has_timed_out() and self.state is ConnectionState.OPEN:
                    self._disconnect(
                        CloseCode.ABNORMAL_CLOSURE
                        if self._timeout_manager.timeout_reason is TimeoutReason.NO_RESPONSE
                        else CloseCode.KEEP_ALIVE_TIMEOUT
                    )
                    continue
                if not readables:
                    self._send_ping_frame()
                    continue
                if self.__cmd_queue in readables:
                    cmd, _, data = self.__cmd_queue.get_nowait()
                    self._process_control_command(cmd, data)
                    if self.state is ConnectionState.CLOSED:
                        continue
                if self.__socket in readables:
                    message = self._process_next_message()
                    if message is not None:
                        yield message
            except Exception as exc:
                self._handle_transport_error(exc)

    def close(self, code, reason=None):
        """Notify the socket to initiate closure. The closing handshake
        will start in the subsequent iteration of the event loop.
        """
        self._send_control_command(ControlCommand.CLOSE, {'code': code, 'reason': reason})

    @classmethod
    def onopen(cls, func):
        cls.__event_callbacks[LifecycleEvent.OPEN].add(func)
        return func

    @classmethod
    def onclose(cls, func):
        cls.__event_callbacks[LifecycleEvent.CLOSE].add(func)
        return func

    def subscribe(self, channels, last):
        """ Subscribe to bus channels. """
        self._channels = channels
        # Only assign the last id according to the client once: the server is
        # more reliable later on, see ``MAX_NOTIFICATION_HISTORY_SEC``.
        if self._last_notif_sent_id == 0:
            self._last_notif_sent_id = last
        # Dispatch past notifications if there are any.
        self.trigger_notification_dispatching()

    def trigger_notification_dispatching(self):
        """
        Warn the socket that notifications are available. Ignore if a
        dispatch is already planned or if the socket is already in the
        closing state.
        """
        if self.state is not ConnectionState.OPEN or self._waiting_for_dispatch:
            return
        self._waiting_for_dispatch = True
        self._send_control_command(ControlCommand.DISPATCH)

    # ------------------------------------------------------
    # PRIVATE METHODS
    # ------------------------------------------------------

    def _get_next_frame(self):
        #     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
        #    +-+-+-+-+-------+-+-------------+-------------------------------+
        #    |F|R|R|R| opcode|M| Payload len |    Extended payload length    |
        #    |I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
        #    |N|V|V|V|       |S|             |   (if payload len==126/127)   |
        #    | |1|2|3|       |K|             |                               |
        #    +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
        #    |     Extended payload length continued, if payload len == 127  |
        #    + - - - - - - - - - - - - - - - +-------------------------------+
        #    |                               |Masking-key, if MASK set to 1  |
        #    +-------------------------------+-------------------------------+
        #    | Masking-key (continued)       |          Payload Data         |
        #    +-------------------------------- - - - - - - - - - - - - - - - +
        #    :                     Payload Data continued ...                :
        #    + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
        #    |                     Payload Data continued ...                |
        #    +---------------------------------------------------------------+
        def recv_bytes(n):
            """ Pull n bytes from the socket """
            data = bytearray()
            while len(data) < n:
                received_data = self.__socket.recv(n - len(data))
                if not received_data:
                    raise ConnectionClosed()
                data.extend(received_data)
            return data

        def is_bit_set(byte, n):
            """
            Check whether nth bit of byte is set or not (from left
            to right).
             """
            return byte & (1 << (7 - n))

        def apply_mask(payload, mask):
            # see: https://www.willmcgugan.com/blog/tech/post/speeding-up-websockets-60x/
            a, b, c, d = (_XOR_TABLE[n] for n in mask)
            payload[::4] = payload[::4].translate(a)
            payload[1::4] = payload[1::4].translate(b)
            payload[2::4] = payload[2::4].translate(c)
            payload[3::4] = payload[3::4].translate(d)
            return payload

        self._limit_rate()
        first_byte, second_byte = recv_bytes(2)
        fin, rsv1, rsv2, rsv3 = (is_bit_set(first_byte, n) for n in range(4))
        try:
            opcode = Opcode(first_byte & 0b00001111)
        except ValueError as exc:
            raise ProtocolError(exc)
        payload_length = second_byte & 0b01111111

        if rsv1 or rsv2 or rsv3:
            raise ProtocolError("Reserved bits must be unset")
        if not is_bit_set(second_byte, 0):
            raise ProtocolError("Frame must be masked")
        if opcode in CTRL_OP:
            if not fin:
                raise ProtocolError("Control frames cannot be fragmented")
            if payload_length > 125:
                raise ProtocolError(
                    "Control frames payload must be smaller than 126"
                )
        if payload_length == 126:
            payload_length = struct.unpack('!H', recv_bytes(2))[0]
        elif payload_length == 127:
            payload_length = struct.unpack('!Q', recv_bytes(8))[0]
        if payload_length > self.MESSAGE_MAX_SIZE:
            raise PayloadTooLargeException()

        mask = recv_bytes(4)
        payload = apply_mask(recv_bytes(payload_length), mask)
        frame = Frame(opcode, bytes(payload), fin, rsv1, rsv2, rsv3)
        self._timeout_manager.acknowledge_frame_receipt(frame)
        return frame

    def _process_next_message(self):
        """
        Process the next message coming throught the socket. If a
        data message can be extracted, return its decoded payload.
        As per the RFC, only control frames will be processed once
        the connection reaches the closing state.
        """
        frame = self._get_next_frame()
        if frame.opcode in CTRL_OP:
            self._handle_control_frame(frame)
            return
        if self.state is not ConnectionState.OPEN:
            # After receiving a control frame indicating the connection
            # should be closed, a peer discards any further data
            # received.
            return
        if frame.opcode is Opcode.CONTINUE:
            raise ProtocolError("Unexpected continuation frame")
        message = frame.payload
        if not frame.fin:
            message = self._recover_fragmented_message(frame)
        return (
            message.decode('utf-8')
            if message is not None and frame.opcode is Opcode.TEXT else message
        )

    def _recover_fragmented_message(self, initial_frame):
        message_fragments = bytearray(initial_frame.payload)
        while True:
            frame = self._get_next_frame()
            if frame.opcode in CTRL_OP:
                # Control frames can be received in the middle of a
                # fragmented message, process them as soon as possible.
                self._handle_control_frame(frame)
                if self.state is not ConnectionState.OPEN:
                    return
                continue
            if frame.opcode is not Opcode.CONTINUE:
                raise ProtocolError("A continuation frame was expected")
            message_fragments.extend(frame.payload)
            if len(message_fragments) > self.MESSAGE_MAX_SIZE:
                raise PayloadTooLargeException()
            if frame.fin:
                return bytes(message_fragments)

    def _send(self, message):
        if self.state is not ConnectionState.OPEN:
            raise InvalidStateException(
                "Trying to send a frame on a closed socket"
            )
        opcode = Opcode.BINARY
        if not isinstance(message, (bytes, bytearray)):
            opcode = Opcode.TEXT
        self._send_frame(Frame(opcode, message))

    def _send_frame(self, frame):
        if frame.opcode in CTRL_OP and len(frame.payload) > 125:
            raise ProtocolError(
                "Control frames should have a payload length smaller than 126"
            )
        if isinstance(frame.payload, str):
            frame.payload = frame.payload.encode('utf-8')
        elif not isinstance(frame.payload, (bytes, bytearray)):
            frame.payload = json.dumps(frame.payload).encode('utf-8')

        output = bytearray()
        first_byte = (
              (0b10000000 if frame.fin else 0)
            | (0b01000000 if frame.rsv1 else 0)
            | (0b00100000 if frame.rsv2 else 0)
            | (0b00010000 if frame.rsv3 else 0)
            | frame.opcode
        )
        payload_length = len(frame.payload)
        if payload_length < 126:
            output.extend(
                struct.pack('!BB', first_byte, payload_length)
            )
        elif payload_length < 65536:
            output.extend(
                struct.pack('!BBH', first_byte, 126, payload_length)
            )
        else:
            output.extend(
                struct.pack('!BBQ', first_byte, 127, payload_length)
            )
        output.extend(frame.payload)
        self.__socket.sendall(output)
        self._timeout_manager.acknowledge_frame_sent(frame)
        if not isinstance(frame, CloseFrame):
            return
        self.state = ConnectionState.CLOSING
        self._close_sent = True
        if frame.code not in CLEAN_CLOSE_CODES or self._close_received:
            return self._terminate()
        # After sending a control frame indicating the connection
        # should be closed, a peer does not send any further data.
        self.__selector.unregister(self.__cmd_queue)

    def _send_close_frame(self, code, reason=None):
        """ Send a close frame. """
        self._send_frame(CloseFrame(code, reason))

    def _send_ping_frame(self):
        """ Send a ping frame """
        self._send_frame(Frame(Opcode.PING))

    def _send_pong_frame(self, payload):
        """ Send a pong frame """
        self._send_frame(Frame(Opcode.PONG, payload))

    def _disconnect(self, code, reason=None):
        """Initiate the closing handshake. Once the acknowledgment is received,
        `self._terminate` will be invoked to execute a graceful shutdown of the
        TCP connection. If the connection is already dead, skip the handshake
        and terminate immediately. This is a low level method, meant to be
        called from the WebSocket event loop. To close the connection, use
        `self.close`.
        """
        if code in (CloseCode.ABNORMAL_CLOSURE, CloseCode.KILL_NOW):
            self._terminate()
        else:
            self._send_close_frame(code, reason)

    def _terminate(self):
        """ Close the underlying TCP socket. """
        with suppress(OSError, TimeoutError):
            self.__socket.shutdown(socket.SHUT_WR)
            # Call recv until obtaining a return value of 0 indicating
            # the other end has performed an orderly shutdown. A timeout
            # is set to ensure the connection will be closed even if
            # the other end does not close the socket properly.
            self.__socket.settimeout(1)
            while self.__socket.recv(4096):
                pass
        with suppress(KeyError):
            self.__selector.unregister(self.__socket)
        self.__selector.close()
        self.__socket.close()
        self.state = ConnectionState.CLOSED
        dispatch.unsubscribe(self)
        self._trigger_lifecycle_event(LifecycleEvent.CLOSE)
        with acquire_cursor(self._db) as cr:
            env = self.new_env(cr, self._session)
            env["ir.websocket"]._on_websocket_closed(self._cookies)

    def _handle_control_frame(self, frame):
        if frame.opcode is Opcode.PING:
            self._send_pong_frame(frame.payload)
        elif frame.opcode is Opcode.CLOSE:
            self.state = ConnectionState.CLOSING
            self._close_received = True
            code, reason = CloseCode.CLEAN, None
            if len(frame.payload) >= 2:
                code = struct.unpack('!H', frame.payload[:2])[0]
                reason = frame.payload[2:].decode('utf-8')
            elif frame.payload:
                raise ProtocolError("Malformed closing frame")
            if not self._close_sent:
                self._send_close_frame(code, reason)
            else:
                self._terminate()

    def _handle_transport_error(self, exc):
        """
        Find out which close code should be sent according to given
        exception and call `self._disconnect` in order to close the
        connection cleanly.
        """
        code, reason = CloseCode.SERVER_ERROR, str(exc)
        if isinstance(exc, (ConnectionClosed, OSError)):
            code = CloseCode.ABNORMAL_CLOSURE
        elif isinstance(exc, (ProtocolError, InvalidCloseCodeException)):
            code = CloseCode.PROTOCOL_ERROR
        elif isinstance(exc, UnicodeDecodeError):
            code = CloseCode.INCONSISTENT_DATA
        elif isinstance(exc, PayloadTooLargeException):
            code = CloseCode.MESSAGE_TOO_BIG
        elif isinstance(exc, (PoolError, RateLimitExceededException)):
            code = CloseCode.TRY_LATER
        elif isinstance(exc, SessionExpiredException):
            code = CloseCode.SESSION_EXPIRED
        if code is CloseCode.SERVER_ERROR:
            reason = None
            registry = Registry(self._session.db)
            sequence = registry.registry_sequence
            registry = registry.check_signaling()
            if sequence != registry.registry_sequence:
                _logger.warning("Bus operation aborted; registry has been reloaded")
            else:
                _logger.error(exc, exc_info=True)
        self._disconnect(code, reason)

    def _limit_rate(self):
        """
        This method is a simple rate limiter designed not to allow
        more than one request by `RL_DELAY` seconds. `RL_BURST` specify
        how many requests can be made in excess of the given rate at the
        begining. When requests are received too fast, raises the
        `RateLimitExceededException`.
        """
        now = time.time()
        if len(self._incoming_frame_timestamps) >= self.RL_BURST:
            elapsed_time = now - self._incoming_frame_timestamps[0]
            if elapsed_time < self.RL_DELAY * self.RL_BURST:
                raise RateLimitExceededException()
        self._incoming_frame_timestamps.append(now)

    def _trigger_lifecycle_event(self, event_type):
        """
        Trigger a lifecycle event that is, call every function
        registered for this event type. Every callback is given both the
        environment and the related websocket.
        """
        if not self.__event_callbacks[event_type]:
            return
        with closing(acquire_cursor(self._db)) as cr:
            env = self.new_env(cr, self._session, set_lang=True)
            for callback in self.__event_callbacks[event_type]:
                try:
                    service_model.retrying(functools.partial(callback, env, self), env)
                except Exception:
                    _logger.warning(
                        'Error during Websocket %s callback',
                        LifecycleEvent(event_type).name,
                        exc_info=True
                    )

    def _send_control_command(self, command, data=None):
        """Send a command to the websocket event loop.

        :param ControlCommand command: The command to be executed.
        :param dict | None data: An optional dictionary of parameters.
        """
        self.__cmd_queue.put((command, next(_command_uid), data))

    def _process_control_command(self, command, data):
        """Process a command received in `self.__cmd_queue`.

        :param ControlCommand command: The command to be executed. This key is required.
        :param dict | None data: An optional dictionary of parameters.
        """
        match command:
            case ControlCommand.DISPATCH:
                self._dispatch_bus_notifications()
            case ControlCommand.CLOSE:
                self._disconnect(data['code'], data.get('reason'))

    def _dispatch_bus_notifications(self):
        """
        Dispatch notifications related to the registered channels. If
        the session is expired, close the connection with the
        `SESSION_EXPIRED` close code. If no cursor can be acquired,
        close the connection with the `TRY_LATER` close code.
        """
        session = root.session_store.get(self._session.sid)
        if not session:
            raise SessionExpiredException()
        if 'next_sid' in session:
            self._session = root.session_store.get(session['next_sid'])
            return self._dispatch_bus_notifications()
         # Mark the notification request as processed.
        self._waiting_for_dispatch = False
        with acquire_cursor(session.db) as cr:
            env = self.new_env(cr, session)
            if session.uid is not None and not check_session(session, env):
                raise SessionExpiredException()
            notifications = env["bus.bus"]._poll(
                self._channels, self._last_notif_sent_id, [n[0] for n in self._notif_history]
            )
        if not notifications:
            return
        for notif in notifications:
            bisect.insort(self._notif_history, (notif["id"], time.time()), key=lambda x: x[0])
        # Discard all the smallest notification ids that have expired and
        # increment the last id accordingly. History can only be trimmed of ids
        # that are below the new last id otherwise some notifications might be
        # dispatched again.
        # For example, if the theshold is 10s, and the state is:
        # last id 2, history [(3, 8s), (6, 10s), (7, 7s)]
        # If 6 is removed because it is above the threshold, the next query will
        # be (id > 2 AND id NOT IN (3, 7)) which will fetch 6 again.
        # 6 can only be removed after 3 reaches the threshold and is removed as
        # well, and if 4 appears in the meantime, 3 can be removed but 6 will
        # have to wait for 4 to reach the threshold as well.
        last_index = -1
        for i, notif in enumerate(self._notif_history):
            if time.time() - notif[1] > self.MAX_NOTIFICATION_HISTORY_SEC:
                last_index = i
            else:
                break
        if last_index != -1:
            self._last_notif_sent_id = self._notif_history[last_index][0]
            self._notif_history = self._notif_history[last_index + 1 :]
        self._send(notifications)

    def new_env(self, cr, session, *, set_lang=False):
        """
        Create a new environment.
        Make sure the transaction has a `default_env` and if requested, set the
        language of the user in the context.
        """
        uid = session.uid
        # lang is not guaranteed to be correct, set None
        ctx = dict(session.context, lang=None)
        env = Environment(cr, uid, ctx)
        if set_lang:
            lang = env['res.lang']._get_code(ctx['lang'])
            env = env(context=dict(ctx, lang=lang))
        if not env.transaction.default_env:
            env.transaction.default_env = env
        return env
