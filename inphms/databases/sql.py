from __future__ import annotations
import typing as t

from .utils import named_to_positional_printf, IDENT_RE

if t.TYPE_CHECKING:
    from inphms.orm.fields import Field
    from collections.abc import Iterable


class SQL:
    """ An object that wraps SQL code with its parameters, like::

        sql = SQL("UPDATE TABLE foo SET a = %s, b = %s", 'hello', 42)
        cr.execute(sql)

        The code is given as a ``%``-format string, and supports either positional
        arguments (with `%s`) or named arguments (with `%(name)s`). The arguments
        are meant to be merged into the code using the `%` formatting operator.
        Note that the character ``%`` must always be escaped (as ``%%``), even if
        the code does not have parameters, like in ``SQL("foo LIKE 'a%%'")``.

        The SQL wrapper is designed to be composable: the arguments can be either
        actual parameters, or SQL objects themselves::

            sql = SQL(
                "UPDATE TABLE %s SET %s",
                SQL.identifier(tablename),
                SQL("%s = %s", SQL.identifier(columnname), value),
            )

        The combined SQL code is given by ``sql.code``, while the corresponding
        combined parameters are given by the list ``sql.params``. This allows to
        combine any number of SQL terms without having to separately combine their
        parameters, which can be tedious, bug-prone, and is the main downside of
        `psycopg2.sql <https://www.psycopg.org/docs/sql.html>`.

        The second purpose of the wrapper is to discourage SQL injections. Indeed,
        if ``code`` is a string literal (not a dynamic string), then the SQL object
        made with ``code`` is guaranteed to be safe, provided the SQL objects
        within its parameters are themselves safe.

        The wrapper may also contain some metadata ``to_flush``.  If not ``None``,
        its value is a field which the SQL code depends on.  The metadata of a
        wrapper and its parts can be accessed by the iterator ``sql.to_flush``.
    """
    __slots__ = ('__code', '__params', '__to_flush')

    __code: str
    __params: tuple
    __to_flush: tuple[Field, ...]

    # pylint: disable=keyword-arg-before-vararg
    def __init__(self, code: (str | SQL) = "", /, *args, to_flush: (Field | Iterable[Field] | None) = None, **kwargs):
        if isinstance(code, SQL):
            if args or kwargs or to_flush:
                raise TypeError("SQL() unexpected arguments when code has type SQL")
            self.__code = code.__code
            self.__params = code.__params
            self.__to_flush = code.__to_flush
            return

        # validate the format of code and parameters
        if args and kwargs:
            raise TypeError("SQL() takes either positional arguments, or named arguments")

        if kwargs:
            code, args = named_to_positional_printf(code, kwargs)
        elif not args:
            code % ()  # check that code does not contain %s
            self.__code = code
            self.__params = ()
            if to_flush is None:
                self.__to_flush = ()
            elif hasattr(to_flush, '__iter__'):
                self.__to_flush = tuple(to_flush)
            else:
                self.__to_flush = (to_flush,)
            return

        code_list = []
        params_list: list = []
        to_flush_list: list = []
        for arg in args:
            if isinstance(arg, SQL):
                code_list.append(arg.__code)
                params_list.extend(arg.__params)
                to_flush_list.extend(arg.__to_flush)
            else:
                code_list.append("%s")
                params_list.append(arg)
        if to_flush is not None:
            if hasattr(to_flush, '__iter__'):
                to_flush_list.extend(to_flush)
            else:
                to_flush_list.append(to_flush)  # type: ignore

        self.__code = code.replace('%%', '%%%%') % tuple(code_list)
        self.__params = tuple(params_list)
        self.__to_flush = tuple(to_flush_list)

    @property
    def code(self) -> str:
        """ Return the combined SQL code string. """
        return self.__code

    @property
    def params(self) -> list:
        """ Return the combined SQL code params as a list of values. """
        return list(self.__params)

    @property
    def to_flush(self) -> Iterable[Field]:
        """ Return an iterator on the fields to flush in the metadata of
        ``self`` and all of its parts.
        """
        return self.__to_flush

    def __repr__(self):
        return f"SQL({', '.join(map(repr, [self.__code, *self.__params]))})"

    def __bool__(self):
        return bool(self.__code)

    def __eq__(self, other):
        return isinstance(other, SQL) and self.__code == other.__code and self.__params == other.__params

    def __hash__(self):
        return hash((self.__code, self.__params))

    def join(self, args: Iterable) -> SQL:
        """ Join SQL objects or parameters with ``self`` as a separator. """
        args = list(args)
        # optimizations for special cases
        if len(args) == 0:
            return SQL()
        if len(args) == 1 and isinstance(args[0], SQL):
            return args[0]
        if not self.__params:
            return SQL(self.__code.join("%s" for arg in args), *args)
        # general case: alternate args with self
        items = [self] * (len(args) * 2 - 1)
        for index, arg in enumerate(args):
            items[index * 2] = arg
        return SQL("%s" * len(items), *items)

    @classmethod
    def identifier(cls, name: str, subname: (str | None) = None, to_flush: (Field | None) = None) -> SQL:
        """ Return an SQL object that represents an identifier. """
        assert name.isidentifier() or IDENT_RE.match(name), f"{name!r} invalid for SQL.identifier()"
        if subname is None:
            return cls(f'"{name}"', to_flush=to_flush)
        assert subname.isidentifier() or IDENT_RE.match(subname), f"{subname!r} invalid for SQL.identifier()"
        return cls(f'"{name}"."{subname}"', to_flush=to_flush)
