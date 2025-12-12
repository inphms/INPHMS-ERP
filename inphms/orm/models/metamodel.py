from __future__ import annotations
import logging
import typing as t
import re
import inspect

from collections import defaultdict

from inphms.orm.fields import Field, Id, Datetime

if t.TYPE_CHECKING:
    from inphms.modules import Registry
    from ..table_objects import TableObject

_logger = logging.getLogger("inphms.models")


class MetaModel(type):
    """ The metaclass of all model classes.
        Its main purpose is to register the models per module.
    """
    _module_to_models__: defaultdict[str, list[MetaModel]] = defaultdict(list)

    pool: Registry | None
    """Reference to the registry for registry classes, otherwise it is a definition class."""

    _field_definitions: list[Field]
    _table_object_definitions: list[TableObject]
    _name: str
    _register: bool  # need to define on each Model, default: True
    _log_access: bool  # when defined, add update log columns
    _module: str | None
    _abstract: bool
    _auto: bool
    _inherit: list[str] | None

    def __new__(meta, name, bases, attrs):
        # this prevents assignment of non-fields on recordsets
        attrs.setdefault('__slots__', ())
        # this collects the fields defined on the class (via Field.__set_name__())
        attrs.setdefault('_field_definitions', [])
        # this collects the table object definitions on the class (via TableObject.__set_name__())
        attrs.setdefault('_table_object_definitions', [])

        if attrs.get('_register', True):
            # determine '_module'
            if '_module' not in attrs:
                module = attrs['__module__']
                assert module.startswith('inphms.addons.'), \
                    f"Invalid import of {module}.{name}, it should start with 'inphms.addons'."
                attrs['_module'] = module.split('.')[2]

            _inherit = attrs.get('_inherit')
            if _inherit and isinstance(_inherit, str):
                attrs.setdefault('_name', _inherit)
                attrs['_inherit'] = [_inherit]

            if not attrs.get('_name'):
                # add '.' before every uppercase letter preceded by any non-underscore char
                attrs['_name'] = re.sub(r"(?<=[^_])([A-Z])", r".\1", name).lower()
                _logger.warning("Class %s has no _name, please make it explicit: _name = %r", name, attrs['_name'])

            assert attrs.get('_name')

        return super().__new__(meta, name, bases, attrs)

    def __init__(self, name, bases, attrs):
        super().__init__(name, bases, attrs)

        if '__init__' in attrs and len(inspect.signature(attrs['__init__']).parameters) != 4:
            _logger.warning("The method %s.__init__ doesn't match the new signature in module %s", name, attrs.get('__module__'))

        if not attrs.get('_register', True):
            return

        # Remember which models to instantiate for this module.
        if self._module:
            self._module_to_models__[self._module].append(self)

        if not self._abstract and self._name not in self._inherit:
            # this class defines a model: add magic fields
            def add(name, field):
                setattr(self, name, field)
                field.__set_name__(self, name)

            def add_default(name, field):
                if name not in attrs:
                    setattr(self, name, field)
                    field.__set_name__(self, name)

            # make sure `id` field is still a `fields.Id`
            if not isinstance(self.id, Id):
                raise TypeError(f"Field {self.id} is not an instance of fields.Id")

            if attrs.get('_log_access', self._auto):
                from ..fields import Many2one  # noqa: PLC0415
                add_default('create_uid', Many2one(
                    'res.users', string='Created by', readonly=True))
                add_default('create_date', Datetime(
                    string='Created on', readonly=True))
                add_default('write_uid', Many2one(
                    'res.users', string='Last Updated by', readonly=True))
                add_default('write_date', Datetime(
                    string='Last Updated on', readonly=True))
