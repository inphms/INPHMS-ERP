from __future__ import annotations
import importlib.metadata
import logging
import functools
import inspect

from . import Response
from .dispatchers import _dispatchers
from .utils import filter_kwargs
from inphms.tools._vendor import parse_version
from inphms.tools import unique


_logger = logging.getLogger("inphms.server.http")

ROUTING_KEYS = {'defaults', 'subdomain', 'build_only',
                'strict_slashes', 'redirect_to',
                'alias', 'host', 'methods',}

if parse_version(importlib.metadata.version('werkzeug')) >= parse_version('2.0.2'):
    # Werkzeug 2.0.2 adds the websocket option. If a websocket request
    # (ws/wss) is trying to access an HTTP route, a WebsocketMismatch
    # exception is raised. On the other hand, Werkzeug 0.16 does not
    # support the websocket routing key. In order to bypass this issue,
    # let's add the websocket key only when appropriate.
    ROUTING_KEYS.add('websocket')


def _generate_routing_rules(modules, nodb_only, converters=None):
    """ Two-fold algorithm used to (1) determine which method in the
        controller inheritance tree should bind to what URL with respect to
        the list of installed modules and (2) merge the various @route
        arguments of said method with the @route arguments of the method it
        overrides.
    """
    def is_valid(cls):
        """ Determine if the class is defined in an addon. """
        path = cls.__module__.split('.')
        return path[:2] == ['inphms', 'addons'] and path[2] in modules

    def get_leaf_classes(cls):
        """ Find the classes that have no child and that have ``cls`` as
            ancestor.
        """
        result = []
        for subcls in cls.__subclasses__():
            if is_valid(subcls):
                result.extend(get_leaf_classes(subcls))
        if not result and is_valid(cls):
            result.append(cls)
        return result

    def build_controllers():
        """ Create dummy controllers that inherit only from the controllers
            defined at the given ``modules`` (often system wide modules or
            installed modules). Modules in this context are Inphms addons.
        """
        from .controller import Controller
        # Controllers defined outside of inphms addons are outside of the
        # controller inheritance/extension mechanism.
        yield from (ctrl() for ctrl in Controller.children_classes.get('', []))

        # Controllers defined inside of inphms addons can be extended in
        # other installed addons. Rebuild the class inheritance here.
        highest_controllers = []
        for module in modules:
            highest_controllers.extend(Controller.children_classes.get(module, []))

        for top_ctrl in highest_controllers:
            leaf_controllers = list(unique(get_leaf_classes(top_ctrl)))

            name = top_ctrl.__name__
            if leaf_controllers != [top_ctrl]:
                name += ' (extended by %s)' %  ', '.join(
                    bot_ctrl.__name__
                    for bot_ctrl in leaf_controllers
                    if bot_ctrl is not top_ctrl
                )

            Ctrl = type(name, tuple(reversed(leaf_controllers)), {})
            yield Ctrl()

    for ctrl in build_controllers():
        for method_name, method in inspect.getmembers(ctrl, inspect.ismethod):

            # Skip this method if it is not @route decorated anywhere in
            # the hierarchy
            def is_method_a_route(cls):
                return getattr(getattr(cls, method_name, None), 'original_routing', None) is not None
            if not any(map(is_method_a_route, type(ctrl).mro())):
                continue

            merged_routing = {
                # 'type': 'http',  # set below
                'auth': 'user',
                'methods': None,
                'routes': [],
            }

            for cls in unique(reversed(type(ctrl).mro()[:-2])):  # ancestors first
                if method_name not in cls.__dict__:
                    continue
                submethod = getattr(cls, method_name)

                if not hasattr(submethod, 'original_routing'):
                    _logger.warning("The endpoint %s is not decorated by @route(), decorating it myself.", f'{cls.__module__}.{cls.__name__}.{method_name}')
                    submethod = route()(submethod)

                _check_and_complete_route_definition(cls, submethod, merged_routing)

                merged_routing.update(submethod.original_routing)

            if not merged_routing['routes']:
                _logger.warning("%s is a controller endpoint without any route, skipping.", f'{cls.__module__}.{cls.__name__}.{method_name}')
                continue

            if nodb_only and merged_routing['auth'] != "none":
                continue

            for url in merged_routing['routes']:
                # duplicates the function (partial) with a copy of the
                # original __dict__ (update_wrapper) to keep a reference
                # to `original_routing` and `original_endpoint`, assign
                # the merged routing ONLY on the duplicated function to
                # ensure method's immutability.
                endpoint = functools.partial(method)
                functools.update_wrapper(endpoint, method)
                endpoint.routing = merged_routing

                yield (url, endpoint)


def route(route=None, **routing):
    """ Decorate a controller method in order to route incoming requests
        matching the given URL and options to the decorated method.

        .. warning::
            It is mandatory to re-decorate any method that is overridden in
            controller extensions but the arguments can be omitted. See
            :class:`~inphms.http.Controller` for more details.
        
        Example::

            @route(route:Iterable[str] | str,
                type:Literal['jsonrpc', 'http'],]
                auth:Literal['user', 'bearer', 'public', 'none'],
                methods:Iterable[str] | None,
                cors:str | None,
                csrf:bool,
                readonly:bool | Callable[[registry, request], bool],
                handle_params_access_error:Callable[[Exception], Response],
                captcha:str | None,
                save_session:bool) -> Response:
                ...
    """
    def decorator(endpoint):
        fname = f"<function {endpoint.__module__}.{endpoint.__name__}>"
        assert routing.get('type', 'http') in _dispatchers.keys(), \
            f"@route(type={routing['type']!r}) is not one of {_dispatchers.keys()}"
        if route:
            routing['routes'] = [route] if isinstance(route, str) else route
        wrong = routing.pop('method', None)
        if wrong is not None:
            _logger.warning("%s defined with invalid routing parameter 'method', assuming 'methods'", fname)
            routing['methods'] = wrong
        if routing.get('auth') == 'bearer':
            routing.setdefault('save_session', False)  # stateless

        @functools.wraps(endpoint)
        def route_wrapper(self, *args, **params):
            params_ok = filter_kwargs(endpoint, params)
            params_ko = set(params) - set(params_ok)
            if params_ko:
                _logger.warning("%s called ignoring args %s", fname, params_ko)

            result = endpoint(self, *args, **params_ok)
            if routing['type'] == 'http':  # _generate_routing_rules() ensures type is set
                return Response.load(result)
            return result

        route_wrapper.original_routing = routing
        route_wrapper.original_endpoint = endpoint
        return route_wrapper
    return decorator


def _check_and_complete_route_definition(controller_cls, submethod, merged_routing):
    """ Verify and complete the route definition. """
    default_type = submethod.original_routing.get('type', 'http')
    routing_type = merged_routing.setdefault('type', default_type)
    if submethod.original_routing.get('type') not in (None, routing_type):
        _logger.warning(
            "The endpoint %s changes the route type, using the original type: %r.",
            f'{controller_cls.__module__}.{controller_cls.__name__}.{submethod.__name__}',
            routing_type)
    submethod.original_routing['type'] = routing_type

    default_auth = submethod.original_routing.get('auth', merged_routing['auth'])
    default_mode = submethod.original_routing.get('readonly', default_auth == 'none')
    parent_readonly = merged_routing.setdefault('readonly', default_mode)
    child_readonly = submethod.original_routing.get('readonly')
    if child_readonly not in (None, parent_readonly) and not callable(child_readonly):
        _logger.warning(
            "The endpoint %s made the route %s altough its parent was defined as %s. Setting the route read/write.",
            f'{controller_cls.__module__}.{controller_cls.__name__}.{submethod.__name__}',
            'readonly' if child_readonly else 'read/write',
            'readonly' if parent_readonly else 'read/write',
        )
        submethod.original_routing['readonly'] = False

