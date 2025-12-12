from __future__ import annotations
import time
import json

from functools import wraps
from passlib.context import CryptContext as _CryptContext

from inphms.server.utils import request
from inphms.exceptions import UserError
from inphms.tools import _


############
# IDENTITY #
############
def _jsonable(o):
    try:
        json.dumps(o)
    except TypeError:
        return False
    else:
        return True

def check_identity(fn):
    """ Wrapped method should be an *action method* (called from a button
    type=object), and requires extra security to be executed. This decorator
    checks if the identity (password) has been checked in the last 10mn, and
    pops up an identity check wizard if not.

    Prevents access outside of interactive contexts (aka with a request)
    """
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        if not request:
            raise UserError(_("This method can only be accessed over HTTP"))

        if request.session.get('identity-check-last', 0) > time.time() - 10 * 60:
            # update identity-check-last like github?
            return fn(self, *args, **kwargs)

        w = self.sudo().env['res.users.identitycheck'].create({
            'request': json.dumps([
                { # strip non-jsonable keys (e.g. mapped to recordsets)
                    k: v for k, v in self.env.context.items()
                    if _jsonable(v)
                },
                self._name,
                self.ids,
                fn.__name__,
                args,
                kwargs
            ])
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users.identitycheck',
            'res_id': w.id,
            'name': _("Access Control"),
            'target': 'new',
            'views': [(False, 'form')],
            'context': {'dialog_size': 'medium'},
        }
    wrapped.__has_check_identity = True
    return wrapped

#################
# CRYPT CONTEXT #
#################
MIN_ROUNDS = 600_000

class CryptContext:
    def __init__(self, *args, **kwargs):
        self.__obj__ = _CryptContext(*args, **kwargs)

    def copy(self):
        """
            The copy method must create a new instance of the
            ``CryptContext`` wrapper with the same configuration
            as the original (``__obj__``).

            There are no need to manage the case where kwargs are
            passed to the ``copy`` method.

            It is necessary to load the original ``CryptContext`` in
            the new instance of the original ``CryptContext`` with ``load``
            to get the same configuration.
        """
        other_wrapper = CryptContext(_autoload=False)
        other_wrapper.__obj__.load(self.__obj__)
        return other_wrapper

    @property
    def hash(self):
        return self.__obj__.hash

    @property
    def identify(self):
        return self.__obj__.identify

    @property
    def verify(self):
        return self.__obj__.verify

    @property
    def verify_and_update(self):
        return self.__obj__.verify_and_update

    def schemes(self):
        return self.__obj__.schemes()

    def update(self, **kwargs):
        if kwargs.get("schemes"):
            assert isinstance(kwargs["schemes"], str) or all(isinstance(s, str) for s in kwargs["schemes"])
        return self.__obj__.update(**kwargs)
