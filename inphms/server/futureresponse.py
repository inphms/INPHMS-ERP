from __future__ import annotations
import werkzeug
import werkzeug.datastructures
import functools
from datetime import datetime, timedelta

from .utils import request

class FutureResponse:
    """ werkzeug.Response mock class that only serves as placeholder for
        headers to be injected in the final response.
    """
    # used by werkzeug.Response.set_cookie
    charset = 'utf-8'
    max_cookie_size = 4093

    def __init__(self):
        self.headers = werkzeug.datastructures.Headers()

    @property
    def _charset(self):
        return self.charset

    @functools.wraps(werkzeug.Response.set_cookie)
    def set_cookie(self, key, value='', max_age=None, expires=-1, path='/', domain=None, secure=False, httponly=False, samesite=None, cookie_type='required'):
        if expires == -1:  # not forced value -> default value -> 1 year
            expires = datetime.now() + timedelta(days=365)

        if request.db and not request.env['ir.http']._is_allowed_cookie(cookie_type):
            max_age = 0
        werkzeug.Response.set_cookie(self, key, value=value, max_age=max_age, expires=expires, path=path, domain=domain, secure=secure, httponly=httponly, samesite=samesite)
