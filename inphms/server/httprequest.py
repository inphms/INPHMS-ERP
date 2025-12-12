from __future__ import annotations
import logging
import werkzeug
import werkzeug.datastructures

from inphms.server.utils import DEFAULT_MAX_CONTENT_LENGTH
from inphms.tools._vendor.useragents import UserAgent

_logger = logging.getLogger("inphms.server.http")


class HTTPRequest:
    def __init__(self, environ):
        httprequest = werkzeug.wrappers.Request(environ)
        httprequest.user_agent_class = UserAgent  # use vendored userAgent since it will be removed in 2.1
        httprequest.parameter_storage_class = werkzeug.datastructures.ImmutableMultiDict
        httprequest.max_content_length = DEFAULT_MAX_CONTENT_LENGTH
        httprequest.max_form_memory_size = 10 * 1024 * 1024  # 10 MB
        self._session_id__ = httprequest.cookies.get('session_id')

        self.__wrapped = httprequest
        self.__environ = self.__wrapped.environ
        self.environ = self.headers.environ = {key: value for key, value in self.__environ.items()
                                               if (not key.startswith(('werkzeug.', 'wsgi.', 'socket')) or key in ['wsgi.url_scheme', 'werkzeug.proxy_fix.orig'])}

    def __enter__(self):
        return self


HTTPREQUEST_ATTRIBUTES = [
    '__str__', '__repr__', '__exit__',
    'accept_charsets', 'accept_languages', 'accept_mimetypes', 'access_route', 'args', 'authorization', 'base_url',
    'charset', 'content_encoding', 'content_length', 'content_md5', 'content_type', 'cookies', 'data', 'date',
    'encoding_errors', 'files', 'form', 'full_path', 'get_data', 'get_json', 'headers', 'host', 'host_url', 'if_match',
    'if_modified_since', 'if_none_match', 'if_range', 'if_unmodified_since', 'is_json', 'is_secure', 'json',
    'max_content_length', 'method', 'mimetype', 'mimetype_params', 'origin', 'path', 'pragma', 'query_string', 'range',
    'referrer', 'remote_addr', 'remote_user', 'root_path', 'root_url', 'scheme', 'script_root', 'server', 'session',
    'trusted_hosts', 'url', 'url_charset', 'url_root', 'user_agent', 'values',
]

def make_request_wrap_methods(attr):
    def getter(self):
        return getattr(self._HTTPRequest__wrapped, attr)

    def setter(self, value):
        return setattr(self._HTTPRequest__wrapped, attr, value)

    return getter, setter

for attr in HTTPREQUEST_ATTRIBUTES:
    setattr(HTTPRequest, attr, property(*make_request_wrap_methods(attr)))