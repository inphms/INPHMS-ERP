from __future__ import annotations

from ..selection import Selection
from ..field import Field
from inphms.databases.sqlutils import pg_varchar

class Reference(Selection):
    """ Pseudo-relational field (no FK in database).

        The field value is stored as a :class:`string <str>` following the pattern
        ``"res_model,res_id"`` in database.
    """
    type = 'reference'

    _column_type = ('varchar', pg_varchar())

    def convert_to_column(self, value, record, values=None, validate=True):
        return Field.convert_to_column(self, value, record, values, validate)

    def convert_to_cache(self, value, record, validate=True):
        # cache format: str ("model,id") or None
        from ...models import BaseModel
        if isinstance(value, BaseModel):
            if not validate or (value._name in self.get_values(record.env) and len(value) <= 1):
                return "%s,%s" % (value._name, value.id) if value else None
        elif isinstance(value, str):
            res_model, res_id = value.split(',')
            if not validate or res_model in self.get_values(record.env):
                if record.env[res_model].browse(int(res_id)).exists():
                    return value
                else:
                    return None
        elif not value:
            return None
        raise ValueError("Wrong value for %s: %r" % (self, value))

    def convert_to_record(self, value, record):
        if value:
            res_model, res_id = value.split(',')
            return record.env[res_model].browse(int(res_id))
        return None

    def convert_to_read(self, value, record, use_display_name=True):
        return "%s,%s" % (value._name, value.id) if value else False

    def convert_to_export(self, value, record):
        return value.display_name if value else ''

    def convert_to_display_name(self, value, record):
        return value.display_name if value else False
