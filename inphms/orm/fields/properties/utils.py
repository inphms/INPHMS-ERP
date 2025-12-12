from __future__ import annotations
import re
import contextlib

from collections import abc

from inphms.tools import frozendict


regex_alphanumeric = re.compile(r'^[a-z0-9_]+$')

def check_property_field_value_name(property_name):
    if not (0 < len(property_name) <= 512) or not regex_alphanumeric.match(property_name):
        raise ValueError(f"Wrong property field value name {property_name!r}.")


class Property(abc.Mapping):
    """Represent a collection of properties of a record.

    An object that implements the value of a :class:`Properties` field in the "record"
    format, i.e., the result of evaluating an expression like ``record.property_field``.
    The value behaves as a ``dict``, and individual properties are returned in their
    expected type, according to ORM conventions.  For instance, the value of a many2one
    property is returned as a recordset::

        # attributes is a properties field, and 'partner_id' is a many2one property;
        # partner is thus a recordset
        partner = record.attributes['partner_id']
        partner.name

    When the accessed key does not exist, i.e., there is no corresponding property
    definition for that record, the access raises a :class:`KeyError`.
    """

    def __init__(self, values, field, record):
        self._values = values
        self.record = record
        self.field = field

    def __iter__(self):
        for key in self._values:
            with contextlib.suppress(KeyError):
                self[key]
                yield key

    def __len__(self):
        return len(self._values)

    def __eq__(self, other):
        return self._values == (other._values if isinstance(other, Property) else other)

    def __getitem__(self, property_name):
        """Will make the verification."""
        if not self.record:
            return False

        values = self.field.convert_to_read(
            self._values,
            self.record,
            use_display_name=False,
        )
        prop = next((p for p in values if p['name'] == property_name), False)
        if not prop:
            raise KeyError(property_name)

        if prop.get('type') == 'many2one' and prop.get('comodel'):
            return self.record.env[prop.get('comodel')].browse(prop.get('value'))

        if prop.get('type') == 'many2many' and prop.get('comodel'):
            return self.record.env[prop.get('comodel')].browse(prop.get('value'))

        if prop.get('type') == 'selection' and prop.get('value'):
            return next((sel[1] for sel in prop.get('selection') if sel[0] == prop['value']), False)

        if prop.get('type') == 'tags' and prop.get('value'):
            return ', '.join(tag[1] for tag in prop.get('tags') if tag[0] in prop['value'])

        return prop.get('value') or False

    def __hash__(self):
        return hash(frozendict(self._values))
