from __future__ import annotations

from operator import attrgetter

from .basestring import BaseString
from inphms.databases import sqlutils

class Char(BaseString):
    """ Basic string field, can be length-limited, usually displayed as a
        single-line string in clients.

        :param int size: the maximum size of values stored for that field

        :param bool trim: states whether the value is trimmed or not (by default,
            ``True``). Note that the trim operation is applied by both the server code and the web client
            This ensures consistent behavior between imported data and UI-entered data.

            - The web client trims user input during in write/create flows in UI.
            - The server trims values during import (in `base_import`) to avoid discrepancies between
            trimmed form inputs and stored DB values.

        :param translate: enable the translation of the field's values; use
            ``translate=True`` to translate field values as a whole; ``translate``
            may also be a callable such that ``translate(callback, value)``
            translates ``value`` by using ``callback(term)`` to retrieve the
            translation of terms.
        :type translate: bool or callable
    """
    type = 'char'
    trim: bool = True                   # whether value is trimmed (only by web client and base_import)

    def _setup_attrs__(self, model_class, name):
        super()._setup_attrs__(model_class, name)
        assert self.size is None or isinstance(self.size, int), \
            "Char field %s with non-integer size %r" % (self, self.size)

    @property
    def _column_type(self):
        return ('varchar', sqlutils.pg_varchar(self.size))

    def update_db_column(self, model, column):
        if (
            column and self.column_type[0] == 'varchar' and
            column['udt_name'] == 'varchar' and column['character_maximum_length'] and
            (self.size is None or column['character_maximum_length'] < self.size)
        ):
            # the column's varchar size does not match self.size; convert it
            sqlutils.convert_column(model.env.cr, model._table, self.name, self.column_type[1])
        super().update_db_column(model, column)

    _related_size = property(attrgetter('size'))
    _related_trim = property(attrgetter('trim'))
    _description_size = property(attrgetter('size'))
    _description_trim = property(attrgetter('trim'))

    def get_depends(self, model):
        depends, depends_context = super().get_depends(model)

        # display_name may depend on context['lang'] (`test_lp1071710`)
        if (
            self.name == 'display_name'
            and self.compute
            and not self.store
            and model._rec_name
            and model._fields[model._rec_name].base_field.translate
            and 'lang' not in depends_context
        ):
            depends_context = [*depends_context, 'lang']

        return depends, depends_context
