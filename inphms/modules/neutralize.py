from __future__ import annotations
import logging
import typing as t

from contextlib import suppress

from inphms.tools import file_open

if t.TYPE_CHECKING:
    from inphms.databases import Cursor
    from collections.abc import Iterable, Iterator

_logger = logging.getLogger(__name__)

__all__ = ["get_installed_modules", "get_neutralization_queries",
           "neutralize_database"]

def get_installed_modules(cursor: Cursor) -> list[str]:
    cursor.execute('''
        SELECT name
          FROM ir_module_module
         WHERE state IN ('installed', 'to upgrade', 'to remove');
    ''')
    return [result[0] for result in cursor.fetchall()]


def get_neutralization_queries(modules: Iterable[str]) -> Iterator[str]:
    # neutralization for each module
    for module in modules:
        filename = f'{module}/data/neutralize.sql'
        with suppress(FileNotFoundError):
            with file_open(filename) as file:
                yield file.read().strip()


def neutralize_database(cursor: Cursor) -> None:
    installed_modules = get_installed_modules(cursor)
    queries = get_neutralization_queries(installed_modules)
    for query in queries:
        cursor.execute(query)
    _logger.info("Neutralization finished")