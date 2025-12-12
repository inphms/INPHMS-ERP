from __future__ import annotations
import typing as t

from xmlrpc.client import MAXINT

from ..field import Field

if t.TYPE_CHECKING:
    from inphms.orm.models import BaseModel

class Integer(Field[int]):
    """ Encapsulates an :class:`int`. """
    type = 'integer'
    _column_type = ('int4', 'int4')
    falsy_value = 0

    aggregator = 'sum'

    def _get_attrs(self, model_class, name):
        res = super()._get_attrs(model_class, name)
        # The default aggregator is None for sequence fields
        if 'aggregator' not in res and name == 'sequence':
            res['aggregator'] = None
        return res

    def convert_to_column(self, value, record, values=None, validate=True):
        return int(value or 0)

    def convert_to_cache(self, value, record, validate=True):
        if isinstance(value, dict):
            # special case, when an integer field is used as inverse for a one2many
            return value.get('id', None)
        return int(value or 0)

    def convert_to_record(self, value, record):
        return value or 0

    def convert_to_read(self, value, record, use_display_name=True):
        # Integer values greater than 2^31-1 are not supported in pure XMLRPC,
        # so we have to pass them as floats :-(
        if value and value > MAXINT:
            return float(value)
        return value

    def _update_inverse(self, records: BaseModel, value: BaseModel):
        self._update_cache(records, value.id or 0)

    def convert_to_export(self, value, record):
        if value or value == 0:
            return value
        return ''
