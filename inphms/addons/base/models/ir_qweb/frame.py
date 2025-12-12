from __future__ import annotations
import typing as t

from typing import NamedTuple

if t.TYPE_CHECKING:
    from .ir_qweb import IrQweb
    from .callparams import QwebCallParameters
    from .content import QwebContent
    from collections.abc import Iterator


class QwebStackFrame(NamedTuple):
    params: QwebCallParameters | QwebContent
    irQweb: IrQweb
    iterator: Iterator[str | QwebCallParameters | QwebContent]
    values: dict
    options: dict | None

    def __repr__(self):
        return f'<QwebStackFrame {self.params!r}>'
