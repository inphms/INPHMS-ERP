from __future__ import annotations
import logging
import token
import re
import fnmatch
import textwrap
import werkzeug.urls

from itertools import count

from inphms.tools._vendor.safe_eval import _EXPR_OPCODES, to_opcodes, _BLACKLIST, _BUILTINS
from inphms.server.utils import request

_logger = logging.getLogger(__name__)


# QWeb token usefull for generate expression used in `_compile_expr_tokens` method
token.QWEB = token.NT_OFFSET - 1
token.tok_name[token.QWEB] = 'QWEB'


# security safe eval opcodes for generated expression validation, used in `_compile_expr`
_SAFE_QWEB_OPCODES = _EXPR_OPCODES.union(to_opcodes([
    'MAKE_FUNCTION', 'CALL_FUNCTION', 'CALL_FUNCTION_KW', 'CALL_FUNCTION_EX',
    'CALL_METHOD', 'LOAD_METHOD',

    'GET_ITER', 'FOR_ITER', 'YIELD_VALUE',
    'JUMP_FORWARD', 'JUMP_ABSOLUTE', 'JUMP_BACKWARD',
    'JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP', 'POP_JUMP_IF_FALSE', 'POP_JUMP_IF_TRUE',

    'LOAD_NAME', 'LOAD_ATTR',
    'LOAD_FAST', 'STORE_FAST', 'UNPACK_SEQUENCE',
    'STORE_SUBSCR',
    'LOAD_GLOBAL',
    'EXTENDED_ARG',
    # Following opcodes were added in 3.11 https://docs.python.org/3/whatsnew/3.11.html#new-opcodes
    'RESUME',
    'CALL',
    'PRECALL',
    'PUSH_NULL',
    'KW_NAMES',
    'FORMAT_VALUE', 'BUILD_STRING',
    'RETURN_GENERATOR',
    'SWAP',
    'POP_JUMP_FORWARD_IF_FALSE', 'POP_JUMP_FORWARD_IF_TRUE',
    'POP_JUMP_BACKWARD_IF_FALSE', 'POP_JUMP_BACKWARD_IF_TRUE',
    'POP_JUMP_FORWARD_IF_NONE', 'POP_JUMP_FORWARD_IF_NOT_NONE',
    'POP_JUMP_BACKWARD_IF_NONE', 'POP_JUMP_BACKWARD_IF_NOT_NONE',
    # 3.12 https://docs.python.org/3/whatsnew/3.12.html#new-opcodes
    'END_FOR',
    'LOAD_FAST_AND_CLEAR',
    'POP_JUMP_IF_NOT_NONE', 'POP_JUMP_IF_NONE',
    'RERAISE',
    'CALL_INTRINSIC_1',
    'STORE_SLICE',
    # 3.13
    'CALL_KW', 'LOAD_FAST_LOAD_FAST',
    'STORE_FAST_STORE_FAST', 'STORE_FAST_LOAD_FAST',
    'CONVERT_VALUE', 'FORMAT_SIMPLE', 'FORMAT_WITH_SPEC',
    'SET_FUNCTION_ATTRIBUTE',
])) - _BLACKLIST


# eval to compile generated string python code into binary code, used in `_compile`
unsafe_eval = eval

SUPPORTED_DEBUGGER = {'pdb', 'ipdb', 'wdb', 'pudb'}
from ..utils import EXTERNAL_ASSET, SCRIPT_EXTENSIONS, STYLE_EXTENSIONS, TEMPLATE_EXTENSIONS, ASSET_EXTENSIONS


from inphms.tools.translate import FORMAT_REGEX
VOID_ELEMENTS = frozenset([
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'keygen',
    'link', 'menuitem', 'meta', 'param', 'source', 'track', 'wbr'])
# Terms allowed in addition to AVAILABLE_OBJECTS when compiling python expressions
ALLOWED_KEYWORD = frozenset(['False', 'None', 'True', 'and', 'as', 'elif', 'else', 'for', 'if', 'in', 'is', 'not', 'or'] + list(_BUILTINS))
RSTRIP_REGEXP = re.compile(r'\n[ \t]*$')
LSTRIP_REGEXP = re.compile(r'^[ \t]*\n')
FIRST_RSTRIP_REGEXP = re.compile(r'^(\n[ \t]*)+(\n[ \t])')
VARNAME_REGEXP = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
TO_VARNAME_REGEXP = re.compile(r'[^A-Za-z0-9_]+')
# Attribute name used outside the context of the QWeb.
SPECIAL_DIRECTIVES = {'t-translation', 't-ignore', 't-title'}
# Name of the variable to insert the content in t-call in the template.
# The slot will be replaced by the `t-call` tag content of the caller.
T_CALL_SLOT = '0'

ETREE_TEMPLATE_REF = count()

# Only allow a javascript scheme if it is followed by [ ][window.]history.back()
MALICIOUS_SCHEMES = re.compile(r'javascript:(?!( ?)((window\.)?)history\.back\(\)$)', re.I).findall

def _id_or_xmlid(ref):
    try:
        return int(ref)
    except ValueError:
        return ref


def indent_code(code, level):
    """Indent the code to respect the python syntax."""
    return textwrap.indent(textwrap.dedent(code).strip(), ' ' * 4 * level)


def keep_query(*keep_params, **additional_params):
    """
    Generate a query string keeping the current request querystring's parameters specified
    in ``keep_params`` and also adds the parameters specified in ``additional_params``.

    Multiple values query string params will be merged into a single one with comma seperated
    values.

    The ``keep_params`` arguments can use wildcards too, eg:

        keep_query('search', 'shop_*', page=4)
    """
    if not keep_params and not additional_params:
        keep_params = ('*',)
    params = additional_params.copy()
    qs_keys = list(request.httprequest.args) if request else []
    for keep_param in keep_params:
        for param in fnmatch.filter(qs_keys, keep_param):
            if param not in additional_params and param in qs_keys:
                params[param] = request.httprequest.args.getlist(param)
    return werkzeug.urls.url_encode(params)
