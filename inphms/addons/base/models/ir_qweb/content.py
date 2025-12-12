from __future__ import annotations
import typing as t

from markupsafe import Markup

if t.TYPE_CHECKING:
    from .ir_qweb import IrQweb
    from .callparams import QwebCallParameters


class QwebContent:
    """ QwebContent wraps a snippet to be used as a string value or a fragment.
        If the value is used with a string operation (from a qweb directive
        like `t-att-help="value % 1"`), the QwebContent loads the snippet.
        If the value is inserted in the document (`t-out="value"`), the snippet
        params bubble up to `_render_iterall`.
    """
    irQweb: IrQweb
    html: str | None
    params__: QwebCallParameters  # not available for the python expression inside the xml

    def __init__(self, irQweb: IrQweb, params: QwebCallParameters):
        self.irQweb = irQweb
        self.html = None
        self.params__ = params

    def __str__(self):
        if self.html is None:
            params = self.params__
            self.html = ''.join(self.irQweb._render_iterall(
               params.view_ref, params.method, params.values, params.directive,
            ))
        return self.html

    def __repr__(self):
        return f'<QwebContent {self.params__!r}>'

    def __len__(self):
        return len(str(self))

    def __html__(self):
        return self.__str__()

    def __contains__(self, key):
        return key in Markup(self)

    def __getattr__(self, name):
        return getattr(Markup(self), name)

    def __getitem__(self, key):
        return Markup(self)[key]

    def __add__(self, other):
        return Markup(self).__add__(other)

    def __radd__(self, other):
        return Markup(self).__radd__(other)

    def __mod__(self, other):
        return Markup(self).__mod__(other)

    def __rmod__(self, other):
        return Markup(self).__rmod__(other)
