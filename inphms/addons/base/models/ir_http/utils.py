from __future__ import annotations
import threading
import werkzeug

try:
    from werkzeug.routing import NumberConverter
except ImportError:
    from werkzeug.routing.converters import NumberConverter  # moved in werkzeug 2.2.2

from inphms.modules import Registry, Environment
from inphms.orm import models
from inphms.server.utils import request

# see also mimetypes module: https://docs.python.org/3/library/mimetypes.html and inphms.tools.mimetypes
EXTENSION_TO_WEB_MIMETYPES = {
    '.css': 'text/css',
    '.less': 'text/less',
    '.scss': 'text/scss',
    '.js': 'text/javascript',
    '.xml': 'text/xml',
    '.csv': 'text/csv',
    '.html': 'text/html',
}


################
# CLASS HELPER #
################
class ModelConverter(werkzeug.routing.BaseConverter):
    regex = r'[0-9]+'

    def __init__(self, url_map, model=False):
        super().__init__(url_map)
        self.model = model

        IrHttp = Registry(threading.current_thread().dbname)['ir.http']
        self.slug = IrHttp._slug
        self.unslug = IrHttp._unslug

    def to_python(self, value: str) -> models.BaseModel:
        _uid = RequestUID(value=value, converter=self)
        env = Environment(request.env.cr, _uid, request.env.context)
        return env[self.model].browse(self.unslug(value)[1])

    def to_url(self, value: models.BaseModel) -> str:
        return self.slug(value)


class ModelsConverter(werkzeug.routing.BaseConverter):
    regex = r'[0-9,]+'

    def __init__(self, url_map, model=False):
        super().__init__(url_map)
        self.model = model

    def to_python(self, value: str) -> models.BaseModel:
        _uid = RequestUID(value=value, converter=self)
        env = Environment(request.env.cr, _uid, request.env.context)
        return env[self.model].browse(int(v) for v in value.split(','))

    def to_url(self, value: models.BaseModel) -> str:
        return ",".join(value.ids)


class SignedIntConverter(NumberConverter):
    regex = r'-?\d+'
    num_convert = int


class FasterRule(werkzeug.routing.Rule):
    """
    _compile_builder is a major part of the routing map generation and rules
    are actually not build so often.
    This classe makes calls to _compile_builder lazy
    """
    def _compile_builder(self, append_unknown=True):
        return LazyCompiledBuilder(self, super()._compile_builder, append_unknown)


# Layer 1
class RequestUID(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class LazyCompiledBuilder:
    def __init__(self, rule, _compile_builder, append_unknown):
        self.rule = rule
        self._callable = None
        self._compile_builder = _compile_builder
        self._append_unknown = append_unknown

    def __get__(self, *args):
        # Rule.compile will actually call
        #
        #   self._build = self._compile_builder(False).__get__(self, None)
        #   self._build_unknown = self._compile_builder(True).__get__(self, None)
        #
        # meaning the _build and _build unkown will contain _compile_builder().__get__(self, None).
        # This is why this override of __get__ is needed.
        return self

    def __call__(self, *args, **kwargs):
        if self._callable is None:
            self._callable = self._compile_builder(self._append_unknown).__get__(self.rule, None)
            del self.rule
            del self._compile_builder
            del self._append_unknown
        return self._callable(*args, **kwargs)
