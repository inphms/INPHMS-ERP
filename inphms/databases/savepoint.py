from __future__ import annotations
import uuid
import typing as t

if t.TYPE_CHECKING:
    from .cursor import _CursorProtocol, BaseCursor


class Savepoint:
    """ Reifies an active breakpoint, allows :meth:`BaseCursor.savepoint` users
        to internally rollback the savepoint (as many times as they want) without
        having to implement their own savepointing, or triggering exceptions.

        Should normally be created using :meth:`BaseCursor.savepoint` rather than
        directly.

        The savepoint will be rolled back on unsuccessful context exits
        (exceptions). It will be released ("committed") on successful context exit.
        The savepoint object can be wrapped in ``contextlib.closing`` to
        unconditionally roll it back.

        The savepoint can also safely be explicitly closed during context body. This
        will rollback by default.

        :param BaseCursor cr: the cursor to execute the `SAVEPOINT` queries on
    """

    def __init__(self, cr: _CursorProtocol):
        self.name = str(uuid.uuid1())
        self._cr = cr
        self.closed: bool = False
        cr.execute('SAVEPOINT "%s"' % self.name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close(rollback=exc_type is not None)

    def close(self, *, rollback: bool = True):
        if not self.closed:
            self._close(rollback)

    def rollback(self):
        self._cr.execute('ROLLBACK TO SAVEPOINT "%s"' % self.name)

    def _close(self, rollback: bool):
        if rollback:
            self.rollback()
        self._cr.execute('RELEASE SAVEPOINT "%s"' % self.name)
        self.closed = True


class _FlushingSavepoint(Savepoint):
    def __init__(self, cr: BaseCursor):
        cr.flush()
        super().__init__(cr)

    def rollback(self):
        from .cursor import BaseCursor
        assert isinstance(self._cr, BaseCursor)
        self._cr.clear()
        super().rollback()

    def _close(self, rollback: bool):
        from .cursor import BaseCursor
        assert isinstance(self._cr, BaseCursor)
        try:
            if not rollback:
                self._cr.flush()
        except Exception:
            rollback = True
            raise
        finally:
            super()._close(rollback)
