from __future__ import annotations
import typing as t

import psycopg2


if t.TYPE_CHECKING:
    from collections.abc import Callable

    from inphms.modules import Environment, Registry

    ConstraintMessageType = t.Union[str, Callable[[Environment, psycopg2.extensions.Diagnostics | None], str]]
    IndexDefinitionType = t.Union[str, Callable[[Registry]]]

