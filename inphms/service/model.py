from __future__ import annotations
import logging
import random
import time
import threading

from functools import partial
from psycopg2 import IntegrityError, OperationalError, errorcodes, errors
from collections.abc import Mapping, Sequence

from inphms.modules import Registry, Environment, SUPERUSER_ID
from inphms.exceptions import ConcurrencyError, ValidationError, AccessDenied, UserError, AccessError
from inphms.server.utils import request as _request, thread_local
from inphms.tools import lazy
from inphms.orm.models import BaseModel

_logger = logging.getLogger(__name__)

PG_CONCURRENCY_ERRORS_TO_RETRY = (errorcodes.LOCK_NOT_AVAILABLE, errorcodes.SERIALIZATION_FAILURE, errorcodes.DEADLOCK_DETECTED)
PG_CONCURRENCY_EXCEPTIONS_TO_RETRY = (errors.LockNotAvailable, errors.SerializationFailure, errors.DeadlockDetected)
MAX_TRIES_ON_CONCURRENCY_FAILURE = 5


##############
# DISPATCHER #
##############
def dispatch(method, params):
    db, uid, passwd, model, method_, *args = params
    uid = int(uid)
    if not passwd:
        raise AccessDenied
    # access checked once we open a cursor

    threading.current_thread().dbname = db
    threading.current_thread().uid = uid
    registry = Registry(db).check_signaling()
    try:
        if method == 'execute':
            kw = {}
        elif method == 'execute_kw':
            # accept: (args, kw=None)
            if len(args) == 1:
                args += ({},)
            args, kw = args
            if kw is None:
                kw = {}
        else:
            raise NameError(f"Method not available {method}")  # noqa: TRY301
        with registry.cursor() as cr:
            Environment(cr, SUPERUSER_ID, {})['res.users']._check_uid_passwd(uid, passwd)
            res = execute_cr(cr, uid, model, method_, args, kw)
        registry.signal_changes()
    except Exception:
        registry.reset_changes()
        raise
    return res

# Layer 1
def execute_cr(cr, uid, obj, method, args, kw):
    # clean cache etc if we retry the same transaction
    cr.reset()
    env = Environment(cr, uid, {})
    env.transaction.default_env = env  # ensure this is the default env for the call
    recs = env.get(obj)
    if recs is None:
        raise UserError(f"Object {obj} doesn't exist")  # pylint: disable=missing-gettext
    thread_local.rpc_model_method = f'{obj}.{method}'
    result = retrying(partial(call_kw, recs, method, args, kw), env)
    # force evaluation of lazy values before the cursor is closed, as it would
    # error afterwards if the lazy isn't already evaluated (and cached)
    for l in _traverse_containers(result, lazy):
        _0 = l._value
    if result is None:
        _logger.info('The method %s of the object %s cannot return `None`!', method, obj)
    return result

# Layer 2
def retrying(func, env):
    try:
        for tryno in range(1, MAX_TRIES_ON_CONCURRENCY_FAILURE + 1):
            tryleft = MAX_TRIES_ON_CONCURRENCY_FAILURE - tryno
            try:
                result = func()
                if not env.cr._closed:
                    env.cr.flush()  # submit the changes to the database
                break
            except (IntegrityError, OperationalError, ConcurrencyError) as exc:
                if env.cr._closed:
                    raise
                env.cr.rollback()
                env.transaction.reset()
                env.registry.reset_changes()
                request = _request
                if request:
                    request.session = request._get_session_and_dbname()[0]
                    # Rewind files in case of failure
                    for filename, file in request.httprequest.files.items():
                        if hasattr(file, "seekable") and file.seekable():
                            file.seek(0)
                        else:
                            raise RuntimeError(f"Cannot retry request on input file {filename!r} after serialization failure") from exc
                if isinstance(exc, IntegrityError):
                    model = env['base']
                    for rclass in env.registry.values():
                        if exc.diag.table_name == rclass._table:
                            model = env[rclass._name]
                            break
                    message = env._("The operation cannot be completed: %s", model._sql_error_to_message(exc))
                    raise ValidationError(message) from exc

                if isinstance(exc, PG_CONCURRENCY_EXCEPTIONS_TO_RETRY):
                    error = errorcodes.lookup(exc.pgcode)
                elif isinstance(exc, ConcurrencyError):
                    error = repr(exc)
                else:
                    raise
                if not tryleft:
                    _logger.info("%s, maximum number of tries reached!", error)
                    raise

                wait_time = random.uniform(0.0, 2 ** tryno)
                _logger.info("%s, %s tries left, try again in %.04f sec...", error, tryleft, wait_time)
                time.sleep(wait_time)
        else:
            # handled in the "if not tryleft" case
            raise RuntimeError("unreachable")

    except Exception:
        env.transaction.reset()
        env.registry.reset_changes()
        raise

    if not env.cr.closed:
        env.cr.commit()  # effectively commits and execute post-commits
    env.registry.signal_changes()
    return result

def call_kw(model: BaseModel, name: str, args: list, kwargs: Mapping):
    """ Invoke the given method ``name`` on the recordset ``model``.

    Private methods cannot be called, only ones returned by `get_public_method`.
    """
    method = get_public_method(model, name)

    # get the records and context
    if getattr(method, '_api_model', False):
        # @api.model -> no ids
        recs = model
    else:
        ids, args = args[0], args[1:]
        recs = model.browse(ids)

    # altering kwargs is a cause of errors, for instance when retrying a request
    # after a serialization error: the retry is done without context!
    kwargs = dict(kwargs)
    context = kwargs.pop('context', None) or {}
    recs = recs.with_context(context)

    # call
    _logger.debug("call %s.%s(%s)", recs, method.__name__, Params(args, kwargs))
    result = method(recs, *args, **kwargs)

    # adapt the result
    if name == "create":
        # special case for method 'create'
        result = result.id if isinstance(args[0], Mapping) else result.ids
    elif isinstance(result, BaseModel):
        result = result.ids

    return result

def _traverse_containers(val, type_):
    """ Yields atoms filtered by specified ``type_`` (or type tuple), traverses
    through standard containers (non-string mappings or sequences) *unless*
    they're selected by the type filter
    """
    if isinstance(val, type_):
        yield val
    elif isinstance(val, (str, bytes, BaseModel)):
        return
    elif isinstance(val, Mapping):
        for k, v in val.items():
            yield from _traverse_containers(k, type_)
            yield from _traverse_containers(v, type_)
    elif isinstance(val, Sequence):
        for v in val:
            yield from _traverse_containers(v, type_)

# Layer 3
class Params:
    """Representation of parameters to a function call that can be stringified for display/logging"""
    def __init__(self, args, kwargs):
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        params = [repr(arg) for arg in self.args]
        params.extend(f"{key}={value!r}" for key, value in sorted(self.kwargs.items()))
        return ', '.join(params)


def get_public_method(model: BaseModel, name: str):
    """ Get the public unbound method from a model.

    When the method does not exist or is inaccessible, raise appropriate errors.
    Accessible methods are public (in sense that python defined it:
    not prefixed with "_") and are not decorated with `@api.private`.
    """
    assert isinstance(model, BaseModel)
    e = f"Private methods (such as '{model._name}.{name}') cannot be called remotely."
    if name.startswith('_'):
        raise AccessError(e)

    cls = type(model)
    method = getattr(cls, name, None)
    if not callable(method):
        raise AttributeError(f"The method '{model._name}.{name}' does not exist")  # noqa: TRY004

    for mro_cls in cls.mro():
        if not (cla_method := getattr(mro_cls, name, None)):
            continue
        if getattr(cla_method, '_api_private', False):
            raise AccessError(e)

    return method
