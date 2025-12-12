from __future__ import annotations
import logging

from datetime import datetime, timedelta
import werkzeug.wrappers
import werkzeug.exceptions

from .utils import request
from .facade import Proxy, ProxyFunc, ProxyAttr

_logger = logging.getLogger("inphms.server.http")


class _Response(werkzeug.wrappers.Response):
    """ Outgoing HTTP response with body, status, headers and qweb support. """
    default_mimetype = 'text/html'

    def __init__(self, *args, **kw):
        template = kw.pop('template', None)
        qcontext = kw.pop('qcontext', None)
        uid = kw.pop('uid', None)
        super().__init__(*args, **kw)
        self.set_default(template, qcontext, uid)

    @classmethod
    def load(cls, result, fname="<function>"):
        """ Convert the return value of an endpoint into a Response. """
        if isinstance(result, Response):
            return result

        if isinstance(result, werkzeug.exceptions.HTTPException):
            _logger.warning("%s returns an HTTPException instead of raising it.", fname)
            raise result

        if isinstance(result, werkzeug.wrappers.Response):
            response = cls.force_type(result)
            response.set_default()
            return response

        if isinstance(result, (bytes, str, type(None))):
            return Response(result)

        raise TypeError(f"{fname} returns an invalid value: {result}")

    def set_default(self, template=None, qcontext=None, uid=None):
        self.template = template
        self.qcontext = qcontext or dict()
        self.qcontext['response_template'] = self.template
        self.uid = uid

    @property
    def is_qweb(self):
        return self.template is not None

    def render(self):
        """ Renders the Response's template, returns the result. """
        self.qcontext['request'] = request
        return request.env["ir.ui.view"]._render_template(self.template, self.qcontext)

    def flatten(self):
        """ Forces the rendering of the response's template, sets the result
            as response body and unsets :attr:`.template`
        """
        if self.template:
            self.response.append(self.render())
            self.template = None

    def set_cookie(self, key, value='', max_age=None, expires=-1, path='/', domain=None, secure=False, httponly=False, samesite=None, cookie_type='required'):
        """ The default expires in Werkzeug is None, which means a session cookie.
            We want to continue to support the session cookie, but not by default.
            Now the default is arbitrary 1 year.
            So if you want a cookie of session, you have to explicitly pass expires=None.
        """
        if expires == -1:  # not provided value -> default value -> 1 year
            expires = datetime.now() + timedelta(days=365)

        if request.db and not request.env['ir.http']._is_allowed_cookie(cookie_type):
            max_age = 0
        super().set_cookie(key, value=value, max_age=max_age, expires=expires, path=path, domain=domain, secure=secure, httponly=httponly, samesite=samesite)


class Headers(Proxy):
    _wrapped__ = werkzeug.datastructures.Headers

    __getitem__ = ProxyFunc()
    __repr__ = ProxyFunc(str) # type: ignore
    __setitem__ = ProxyFunc(None)
    __str__ = ProxyFunc(str) # type: ignore
    __contains__ = ProxyFunc(bool)
    add = ProxyFunc(None)
    add_header = ProxyFunc(None)
    clear = ProxyFunc(None)
    copy = ProxyFunc(lambda v: Headers(v))
    extend = ProxyFunc(None)
    get = ProxyFunc()
    get_all = ProxyFunc()
    getlist = ProxyFunc()
    items = ProxyFunc()
    keys = ProxyFunc()
    pop = ProxyFunc()
    popitem = ProxyFunc()
    remove = ProxyFunc(None)
    set = ProxyFunc(None)
    setdefault = ProxyFunc()
    setlist = ProxyFunc(None)
    setlistdefault = ProxyFunc()
    to_wsgi_list = ProxyFunc()
    update = ProxyFunc(None)
    values = ProxyFunc()


class ResponseCacheControl(Proxy):
    _wrapped__ = werkzeug.datastructures.ResponseCacheControl

    __getitem__ = ProxyFunc()
    __setitem__ = ProxyFunc(None)
    immutable = ProxyAttr(bool)
    max_age = ProxyAttr(int)
    must_revalidate = ProxyAttr(bool)
    no_cache = ProxyAttr(bool)
    no_store = ProxyAttr(bool)
    no_transform = ProxyAttr(bool)
    public = ProxyAttr(bool)
    private = ProxyAttr(bool)
    proxy_revalidate = ProxyAttr(bool)
    s_maxage = ProxyAttr(int)
    pop = ProxyFunc()


class ResponseStream(Proxy):
    _wrapped__ = werkzeug.wrappers.ResponseStream # type: ignore

    write = ProxyFunc(int)
    writelines = ProxyFunc(None)
    tell = ProxyFunc(int)


class Response(Proxy):
    _wrapped__ = _Response

    # werkzeug.wrappers.Response attributes
    __call__ = ProxyFunc()
    add_etag = ProxyFunc(None)
    age = ProxyAttr()
    autocorrect_location_header = ProxyAttr(bool)
    cache_control = ProxyAttr(ResponseCacheControl)
    call_on_close = ProxyFunc()
    charset = ProxyAttr(str)
    content_encoding = ProxyAttr(str)
    content_length = ProxyAttr(int)
    content_location = ProxyAttr(str)
    content_md5 = ProxyAttr(str)
    content_type = ProxyAttr(str)
    data = ProxyAttr()
    default_mimetype = ProxyAttr(str)
    default_status = ProxyAttr(int)
    delete_cookie = ProxyFunc(None)
    direct_passthrough = ProxyAttr(bool)
    expires = ProxyAttr()
    force_type = ProxyFunc(lambda v: Response(v))  # noqa: PLW0108
    freeze = ProxyFunc(None)
    get_data = ProxyFunc()
    get_etag = ProxyFunc()
    get_json = ProxyFunc()
    headers = ProxyAttr(Headers)
    is_json = ProxyAttr(bool)
    is_sequence = ProxyAttr(bool)
    is_streamed = ProxyAttr(bool)
    iter_encoded = ProxyFunc()
    json = ProxyAttr()
    last_modified = ProxyAttr()
    location = ProxyAttr(str)
    make_conditional = ProxyFunc(lambda v: Response(v))  # noqa: PLW0108
    make_sequence = ProxyFunc(None)
    max_cookie_size = ProxyAttr(int)
    mimetype = ProxyAttr(str)
    response = ProxyAttr()
    retry_after = ProxyAttr()
    set_cookie = ProxyFunc(None)
    set_data = ProxyFunc(None)
    set_etag = ProxyFunc(None)
    status = ProxyAttr(str)
    status_code = ProxyAttr(int)
    stream = ProxyAttr(ResponseStream)

    # inphms.http._response attributes
    load = ProxyFunc()
    set_default = ProxyFunc(None)
    qcontext = ProxyAttr()
    template = ProxyAttr(str)
    is_qweb = ProxyAttr(bool)
    render = ProxyFunc()
    flatten = ProxyFunc(None)

    def __init__(self, *args, **kwargs):
        response = None
        if len(args) == 1:
            arg = args[0]
            if isinstance(arg, Response):
                response = arg._wrapped__
            elif isinstance(arg, _Response):
                response = arg
            elif isinstance(arg, werkzeug.wrappers.Response):
                response = _Response.load(arg)
        if response is None:
            if isinstance(kwargs.get('headers'), Headers):
                kwargs['headers'] = kwargs['headers']._wrapped__
            response = _Response(*args, **kwargs)

        super().__init__(response)
        if 'set_cookie' in response.__dict__:
            self.__dict__['set_cookie'] = response.__dict__['set_cookie']
