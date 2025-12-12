from __future__ import annotations
import typing as t

from operator import attrgetter

from inphms.tools import Sentinel, SENTINEL, float_repr, float_round, float_is_zero, float_compare
from ..field import Field

if t.TYPE_CHECKING:
    from inphms.modules import Environment

class Float(Field[float]):
    """ Encapsulates a :class:`float`.

        The precision digits are given by the (optional) ``digits`` attribute.

        :param digits: a pair (total, decimal) or a string referencing a
            :class:`~inphms.addons.base.models.decimal_precision.DecimalPrecision` record name.
        :type digits: tuple(int,int) or str

        When a float is a quantity associated with an unit of measure, it is important
        to use the right tool to compare or round values with the correct precision.

        The Float class provides some static methods for this purpose:

        :func:`~inphms.fields.Float.round()` to round a float with the given precision.
        :func:`~inphms.fields.Float.is_zero()` to check if a float equals zero at the given precision.
        :func:`~inphms.fields.Float.compare()` to compare two floats at the given precision.

        .. admonition:: Example

            To round a quantity with the precision of the unit of measure::

                fields.Float.round(self.product_uom_qty, precision_rounding=self.product_uom_id.rounding)

            To check if the quantity is zero with the precision of the unit of measure::

                fields.Float.is_zero(self.product_uom_qty, precision_rounding=self.product_uom_id.rounding)

            To compare two quantities::

                field.Float.compare(self.product_uom_qty, self.qty_done, precision_rounding=self.product_uom_id.rounding)

            The compare helper uses the __cmp__ semantics for historic purposes, therefore
            the proper, idiomatic way to use this helper is like so:

                if result == 0, the first and second floats are equal
                if result < 0, the first float is lower than the second
                if result > 0, the first float is greater than the second
    """

    type = 'float'
    _digits: str | tuple[int, int] | None = None  # digits argument passed to class initializer
    falsy_value = 0.0
    aggregator = 'sum'

    def __init__(self, string: str | Sentinel = SENTINEL, digits: str | tuple[int, int] | Sentinel | None = SENTINEL, **kwargs):
        super().__init__(string=string, _digits=digits, **kwargs)

    @property
    def _column_type(self):
        # Explicit support for "falsy" digits (0, False) to indicate a NUMERIC
        # field with no fixed precision. The values are saved in the database
        # with all significant digits.
        # FLOAT8 type is still the default when there is no precision because it
        # is faster for most operations (sums, etc.)
        return ('numeric', 'numeric') if self._digits is not None else \
               ('float8', 'double precision')

    def get_digits(self, env: Environment) -> tuple[int, int] | None:
        if isinstance(self._digits, str):
            precision = env['decimal.precision'].precision_get(self._digits)
            return 16, precision
        else:
            return self._digits

    _related__digits = property(attrgetter('_digits'))

    def _description_digits(self, env: Environment) -> tuple[int, int] | None:
        return self.get_digits(env)

    def convert_to_column(self, value, record, values=None, validate=True):
        value_float = value = float(value or 0.0)
        if digits := self.get_digits(record.env):
            _precision, scale = digits
            value_float = float_round(value, precision_digits=scale)
            value = float_repr(value_float, precision_digits=scale)
        if self.company_dependent:
            return value_float
        return value

    def convert_to_cache(self, value, record, validate=True):
        # apply rounding here, otherwise value in cache may be wrong!
        value = float(value or 0.0)
        digits = self.get_digits(record.env)
        return float_round(value, precision_digits=digits[1]) if digits else value

    def convert_to_record(self, value, record):
        return value or 0.0

    def convert_to_export(self, value, record):
        if value or value == 0.0:
            return value
        return ''

    round = staticmethod(float_round)
    is_zero = staticmethod(float_is_zero)
    compare = staticmethod(float_compare)
