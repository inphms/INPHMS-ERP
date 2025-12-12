from __future__ import annotations
import random
import time
import logging
import socket
import struct

from queue import PriorityQueue
from contextlib import suppress
from psycopg2.pool import PoolError
from enum import IntEnum
from itertools import count
from weakref import WeakSet
from werkzeug.local import LocalStack

from inphms.server import CommonServer
from inphms.modules import Registry
from .exception import InvalidCloseCodeException
from inphms.config import config

_logger = logging.getLogger(__name__)


#########
# CONST #
#########
MAX_TRY_ON_POOL_ERROR = 10
DELAY_ON_POOL_ERROR = 0.03


##########
# HELPER #
##########
def acquire_cursor(db):
    """ Try to acquire a cursor up to `MAX_TRY_ON_POOL_ERROR` """
    for tryno in range(1, MAX_TRY_ON_POOL_ERROR + 1):
        with suppress(PoolError):
            return Registry(db).cursor()
        time.sleep(random.uniform(DELAY_ON_POOL_ERROR, DELAY_ON_POOL_ERROR * tryno))
    raise PoolError('Failed to acquire cursor after %s retries' % MAX_TRY_ON_POOL_ERROR)


#################
# PrioratyQueue #
#################
# Idea taken from the python cookbook:
# https://github.com/dabeaz/python-cookbook/blob/6e46b7/src/12/polling_multiple_thread_queues/pqueue.py
class PollablePriorityQueue(PriorityQueue):
    """A custom PriorityQueue than can be polled"""

    def __init__(self, maxsize=0):
        super().__init__(maxsize)
        self._putsocket, self._getsocket = socket.socketpair()

    def fileno(self):
        return self._getsocket.fileno()

    def put(self, item, *args, **kwargs):
        super().put(item, *args, **kwargs)
        self._putsocket.send(b'.')

    def get(self, *args, **kwargs):
        self._getsocket.recv(1)
        return super().get(*args, **kwargs)


#######################
# Websocket Lifecycle #
#######################

class LifecycleEvent(IntEnum):
    OPEN = 0
    CLOSE = 1


####################
# Websocket Helper #
####################

class Opcode(IntEnum):
    CONTINUE = 0x00
    TEXT = 0x01
    BINARY = 0x02
    CLOSE = 0x08
    PING = 0x09
    PONG = 0x0A


class CloseCode(IntEnum):
    CLEAN = 1000
    GOING_AWAY = 1001
    PROTOCOL_ERROR = 1002
    INCORRECT_DATA = 1003
    ABNORMAL_CLOSURE = 1006
    INCONSISTENT_DATA = 1007
    MESSAGE_VIOLATING_POLICY = 1008
    MESSAGE_TOO_BIG = 1009
    EXTENSION_NEGOTIATION_FAILED = 1010
    SERVER_ERROR = 1011
    RESTART = 1012
    TRY_LATER = 1013
    BAD_GATEWAY = 1014
    SESSION_EXPIRED = 4001
    KEEP_ALIVE_TIMEOUT = 4002
    KILL_NOW = 4003


class ConnectionState(IntEnum):
    OPEN = 0
    CLOSING = 1
    CLOSED = 2


# Used to maintain order of commands in the queue according to their priority
# (IntEnum) and then the order of reception.
_command_uid = count(0)


class ControlCommand(IntEnum):
    CLOSE = 0
    DISPATCH = 1


DATA_OP = {Opcode.TEXT, Opcode.BINARY}
CTRL_OP = {Opcode.CLOSE, Opcode.PING, Opcode.PONG}
HEARTBEAT_OP = {Opcode.PING, Opcode.PONG}

VALID_CLOSE_CODES = {
    code for code in CloseCode if code is not CloseCode.ABNORMAL_CLOSURE
}
CLEAN_CLOSE_CODES = {CloseCode.CLEAN, CloseCode.GOING_AWAY, CloseCode.RESTART}
RESERVED_CLOSE_CODES = range(3000, 5000)

_XOR_TABLE = [bytes(a ^ b for a in range(256)) for b in range(256)]


class Frame:
    def __init__(
        self,
        opcode,
        payload=b'',
        fin=True,
        rsv1=False,
        rsv2=False,
        rsv3=False
    ):
        self.opcode = opcode
        self.payload = payload
        self.fin = fin
        self.rsv1 = rsv1
        self.rsv2 = rsv2
        self.rsv3 = rsv3


class CloseFrame(Frame):
    def __init__(self, code, reason):
        if code not in VALID_CLOSE_CODES and code not in RESERVED_CLOSE_CODES:
            raise InvalidCloseCodeException(code)
        payload = struct.pack('!H', code)
        if reason:
            payload += reason.encode('utf-8')
        self.code = code
        self.reason = reason
        super().__init__(Opcode.CLOSE, payload)


_websocket_instances = WeakSet()


class TimeoutReason(IntEnum):
    KEEP_ALIVE = 0
    NO_RESPONSE = 1


class TimeoutManager:
    """
    This class handles the Websocket timeouts. If no response to a
    PING/CLOSE frame is received after `TIMEOUT` seconds or if the
    connection is opened for more than `self._keep_alive_timeout` seconds,
    the connection is considered to have timed out. To determine if the
    connection has timed out, use the `has_timed_out` method.
    """
    TIMEOUT = 15
    # Timeout specifying how many seconds the connection should be kept
    # alive.
    KEEP_ALIVE_TIMEOUT = int(config['websocket_keep_alive_timeout'])

    def __init__(self):
        super().__init__()
        self._awaited_opcode = None
        # Time in which the connection was opened.
        self._opened_at = time.time()
        # Custom keep alive timeout for each TimeoutManager to avoid multiple
        # connections timing out at the same time.
        self._keep_alive_timeout = (
            self.KEEP_ALIVE_TIMEOUT + random.uniform(0, self.KEEP_ALIVE_TIMEOUT / 2)
        )
        self.timeout_reason = None
        # Start time recorded when we started awaiting an answer to a
        # PING/CLOSE frame.
        self._waiting_start_time = None

    def acknowledge_frame_receipt(self, frame):
        if self._awaited_opcode is frame.opcode:
            self._awaited_opcode = None
            self._waiting_start_time = None

    def acknowledge_frame_sent(self, frame):
        """
        Acknowledge a frame was sent. If this frame is a PING/CLOSE
        frame, start waiting for an answer.
        """
        if self.has_timed_out():
            return
        if frame.opcode is Opcode.PING:
            self._awaited_opcode = Opcode.PONG
        elif frame.opcode is Opcode.CLOSE:
            self._awaited_opcode = Opcode.CLOSE
        if self._awaited_opcode is not None:
            self._waiting_start_time = time.time()

    def has_timed_out(self):
        """
        Determine whether the connection has timed out or not. The
        connection times out when the answer to a CLOSE/PING frame
        is not received within `TIMEOUT` seconds or if the connection
        is opened for more than `self._keep_alive_timeout` seconds.
        """
        now = time.time()
        if now - self._opened_at >= self._keep_alive_timeout:
            self.timeout_reason = TimeoutReason.KEEP_ALIVE
            return True
        if self._awaited_opcode and now - self._waiting_start_time >= self.TIMEOUT:
            self.timeout_reason = TimeoutReason.NO_RESPONSE
            return True
        return False


_wsrequest_stack = LocalStack()
wsrequest = _wsrequest_stack()

def _kick_all(code=CloseCode.GOING_AWAY):
    """ Disconnect all the websocket instances. """
    for websocket in _websocket_instances:
        if websocket.state is ConnectionState.OPEN:
            websocket.close(code)


CommonServer.on_stop(_kick_all)