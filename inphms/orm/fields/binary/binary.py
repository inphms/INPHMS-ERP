from __future__ import annotations
import functools
import base64
import binascii
import psycopg2
import contextlib
import typing as t

from inphms.tools import human_size
from inphms.tools.mimetypes import guess_mimetype
from inphms.exceptions import UserError
from inphms.databases import SQL
from operator import attrgetter

from ..utils import SQL_OPERATORS
from ..field import Field
from .utils import _BINARY

if t.TYPE_CHECKING:
    from inphms.databases import Query
    from ...models import BaseModel


class Binary(Field):
    """Encapsulates a binary content (e.g. a file).

    :param bool attachment: whether the field should be stored as `ir_attachment`
        or in a column of the model's table (default: ``True``).
    """
    type = 'binary'

    prefetch = False                    # not prefetched by default
    _depends_context = ('bin_size',)    # depends on context (content or size)
    attachment = True                   # whether value is stored in attachment

    @functools.cached_property
    def column_type(self):
        return None if self.attachment else ('bytea', 'bytea')

    def _get_attrs(self, model_class, name):
        attrs = super()._get_attrs(model_class, name)
        if not attrs.get('store', True):
            attrs['attachment'] = False
        return attrs

    _description_attachment = property(attrgetter('attachment'))

    def convert_to_column(self, value, record, values=None, validate=True):
        # Binary values may be byte strings (python 2.6 byte array), but
        # the legacy OpenERP convention is to transfer and store binaries
        # as base64-encoded strings. The base64 string may be provided as a
        # unicode in some circumstances, hence the str() cast here.
        # This str() coercion will only work for pure ASCII unicode strings,
        # on purpose - non base64 data must be passed as a 8bit byte strings.
        if not value:
            return None
        # Detect if the binary content is an SVG for restricting its upload
        # only to system users.
        magic_bytes = {
            b'P',  # first 6 bits of '<' (0x3C) b64 encoded
            b'<',  # plaintext XML tag opening
        }
        if isinstance(value, str):
            value = value.encode()
        if validate and value[:1] in magic_bytes:
            try:
                decoded_value = base64.b64decode(value.translate(None, delete=b'\r\n'), validate=True)
            except binascii.Error:
                decoded_value = value
            # Full mimetype detection
            if (guess_mimetype(decoded_value).startswith('image/svg') and
                    not record.env.is_system()):
                raise UserError(record.env._("Only admins can upload SVG files."))
        if isinstance(value, bytes):
            return psycopg2.Binary(value)
        try:
            return psycopg2.Binary(str(value).encode('ascii'))
        except UnicodeEncodeError:
            raise UserError(record.env._("ASCII characters are required for %(value)s in %(field)s", value=value, field=self.name))

    def get_column_update(self, record: BaseModel):
        # since the field depends on context, force the value where we have the data
        bin_size_name = 'bin_size_' + self.name
        record_no_bin_size = record.with_context(**{'bin_size': False, bin_size_name: False})
        return self._get_cache(record_no_bin_size.env)[record.id]

    def convert_to_cache(self, value, record, validate=True):
        if isinstance(value, _BINARY):
            return bytes(value)
        if isinstance(value, str):
            # the cache must contain bytes or memoryview, but sometimes a string
            # is given when assigning a binary field (test `TestFileSeparator`)
            return value.encode()
        if isinstance(value, int) and \
                (record.env.context.get('bin_size') or
                 record.env.context.get('bin_size_' + self.name)):
            # If the client requests only the size of the field, we return that
            # instead of the content. Presumably a separate request will be done
            # to read the actual content, if necessary.
            value = human_size(value)
            # human_size can return False (-> None) or a string (-> encoded)
            return value.encode() if value else None
        return None if value is False else value

    def convert_to_record(self, value, record):
        if isinstance(value, _BINARY):
            return bytes(value)
        return False if value is None else value

    def compute_value(self, records):
        bin_size_name = 'bin_size_' + self.name
        if records.env.context.get('bin_size') or records.env.context.get(bin_size_name):
            # always compute without bin_size
            records_no_bin_size = records.with_context(**{'bin_size': False, bin_size_name: False})
            super().compute_value(records_no_bin_size)
            # manually update the bin_size cache
            field_cache_data = self._get_cache(records_no_bin_size.env)
            field_cache_size = self._get_cache(records.env)
            for record in records:
                try:
                    value = field_cache_data[record.id]
                    # don't decode non-attachments to be consistent with pg_size_pretty
                    if not (self.store and self.column_type):
                        with contextlib.suppress(TypeError, binascii.Error):
                            value = base64.b64decode(value)
                    try:
                        if isinstance(value, (bytes, _BINARY)):
                            value = human_size(len(value))
                    except (TypeError):
                        pass
                    cache_value = self.convert_to_cache(value, record)
                    # the dirty flag is independent from this assignment
                    field_cache_size[record.id] = cache_value
                except KeyError:
                    pass
        else:
            super().compute_value(records)

    def read(self, records):
        def _encode(s: str | bool) -> bytes | bool:
            if isinstance(s, str):
                return s.encode("utf-8")
            return s

        # values are stored in attachments, retrieve them
        assert self.attachment
        domain = [
            ('res_model', '=', records._name),
            ('res_field', '=', self.name),
            ('res_id', 'in', records.ids),
        ]
        bin_size = records.env.context.get('bin_size')
        data = {
            att.res_id: _encode(human_size(att.file_size)) if bin_size else att.datas
            for att in records.env['ir.attachment'].sudo().search_fetch(domain)
        }
        self._insert_cache(records, map(data.get, records._ids))

    def create(self, record_values):
        assert self.attachment
        if not record_values:
            return
        # create the attachments that store the values
        env = record_values[0][0].env
        env['ir.attachment'].sudo().create([
            {
                'name': self.name,
                'res_model': self.model_name,
                'res_field': self.name,
                'res_id': record.id,
                'type': 'binary',
                'datas': value,
            }
            for record, value in record_values
            if value
        ])

    def write(self, records, value):
        records = records.with_context(bin_size=False)
        if not self.attachment:
            super().write(records, value)
            return

        # discard recomputation of self on records
        records.env.remove_to_compute(self, records)

        # update the cache, and discard the records that are not modified
        cache_value = self.convert_to_cache(value, records)
        records = self._filter_not_equal(records, cache_value)
        if not records:
            return
        if self.store:
            # determine records that are known to be not null
            not_null = self._filter_not_equal(records, None)

        self._update_cache(records, cache_value)

        # retrieve the attachments that store the values, and adapt them
        if self.store and any(records._ids):
            real_records = records.filtered('id')
            atts = records.env['ir.attachment'].sudo()
            if not_null:
                atts = atts.search([
                    ('res_model', '=', self.model_name),
                    ('res_field', '=', self.name),
                    ('res_id', 'in', real_records.ids),
                ])
            if value:
                # update the existing attachments
                atts.write({'datas': value})
                atts_records = records.browse(atts.mapped('res_id'))
                # create the missing attachments
                missing = (real_records - atts_records)
                if missing:
                    atts.create([{
                            'name': self.name,
                            'res_model': record._name,
                            'res_field': self.name,
                            'res_id': record.id,
                            'type': 'binary',
                            'datas': value,
                        }
                        for record in missing
                    ])
            else:
                atts.unlink()

    def condition_to_sql(self, field_expr: str, operator: str, value, model: BaseModel, alias: str, query: Query) -> SQL:
        if not self.attachment or field_expr != self.name:
            return super().condition_to_sql(field_expr, operator, value, model, alias, query)
        assert operator in ('in', 'not in') and set(value) == {False}, "Should have been done in Domain optimization"
        return SQL(
            "%s%s(SELECT res_id FROM ir_attachment WHERE res_model = %s AND res_field = %s)",
            model._field_to_sql(alias, 'id', query),
            SQL_OPERATORS['not in' if operator in ('in', '=') else 'in'],
            model._name,
            self.name,
        )
