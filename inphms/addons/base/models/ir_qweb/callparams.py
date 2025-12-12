from __future__ import annotations

from typing import Literal, NamedTuple


class QwebCallParameters(NamedTuple):
    context: dict
    view_ref: str | int
    method: str | None
    values: dict | None
    scope: bool | Literal['root']
    directive: str
    path_xml: tuple[str | int, str, str] | None

    def __repr__(self):
        # cleaning context and values in order to have a consistent log when debugging.
        context = {k: v for k, v in self.context.items() if not k.startswith('_')}
        qweb_root_values = self.values.get('__qweb_root_values') or {}
        values = self.values and {
            k: v for k, v in self.values.items()
            if k not in ('__qweb_root_values', '__qweb_attrs__')
            if v is not qweb_root_values.get(k)
        }
        return (
            f"<QwebCallParameters context={context!r} view_ref={self.view_ref!r}"
            f" method={self.method!r} values={values!r} scope={self.scope!r}"
            f" directive={self.directive!r} path_xml={self.path_xml!r}>"
        )
