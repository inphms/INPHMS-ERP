from __future__ import annotations
import json
import ast
import copy

from ...domains import Domain
from ..field import Field
from .utils import check_property_field_value_name
from .prop import Properties
from inphms.tools import html_sanitize, is_list_of


NoneType = type(None)


class PropertiesDefinition(Field):
    """ Field used to define the properties definition (see :class:`~inphms.fields.Properties`
    field). This field is used on the container record to define the structure
    of expected properties on subrecords. It is used to check the properties
    definition. """
    type = 'properties_definition'
    _column_type = ('jsonb', 'jsonb')
    copy = True                         # containers may act like templates, keep definitions to ease usage
    readonly = False
    prefetch = True
    properties_fields = ()  # List of Properties fields using that definition

    REQUIRED_KEYS = ('name', 'type')
    ALLOWED_KEYS = (
        'name', 'string', 'type', 'comodel', 'default', 'suffix',
        'selection', 'tags', 'domain', 'view_in_cards', 'fold_by_default',
        'currency_field'
    )
    # those keys will be removed if the types does not match
    PROPERTY_PARAMETERS_MAP = {
        'comodel': {'many2one', 'many2many'},
        'currency_field': {'monetary'},
        'domain': {'many2one', 'many2many'},
        'selection': {'selection'},
        'tags': {'tags'},
    }

    def convert_to_column(self, value, record, values=None, validate=True):
        """Convert the value before inserting it in database.

        This method accepts a list properties definition.

        The relational properties (many2one / many2many) default value
        might contain the display_name of those records (and will be removed).

        [{
            'name': '3adf37f3258cfe40',
            'string': 'Color Code',
            'type': 'char',
            'default': 'blue',
            'value': 'red',
        }, {
            'name': 'aa34746a6851ee4e',
            'string': 'Partner',
            'type': 'many2one',
            'comodel': 'test_orm.partner',
            'default': [1337, 'Bob'],
        }]
        """
        if not value:
            return None

        if isinstance(value, str):
            value = json.loads(value)

        if not isinstance(value, list):
            raise TypeError(f'Wrong properties definition type {type(value)!r}')

        if validate:
            Properties._remove_display_name(value, value_key='default')

            self._validate_properties_definition(value, record.env)

        return json.dumps(record._convert_to_cache_properties_definition(value))

    def convert_to_cache(self, value, record, validate=True):
        # any format -> cache format (list of dicts or None)
        if not value:
            return None

        if isinstance(value, list):
            # avoid accidental side effects from shared mutable data, and make
            # the value strict with respect to JSON (tuple -> list, etc)
            value = json.dumps(value)

        if isinstance(value, str):
            value = json.loads(value)

        if not isinstance(value, list):
            raise TypeError(f'Wrong properties definition type {type(value)!r}')

        if validate:
            Properties._remove_display_name(value, value_key='default')

            self._validate_properties_definition(value, record.env)

        return record._convert_to_column_properties_definition(value)

    def convert_to_record(self, value, record):
        # cache format -> record format (list of dicts)
        if not value:
            return []

        # return a copy of the definition in cache where all property
        # definitions have been cleaned up
        result = []

        for property_definition in value:
            if not all(property_definition.get(key) for key in self.REQUIRED_KEYS):
                # some required keys are missing, ignore this property definition
                continue

            # don't modify the value in cache
            property_definition = copy.deepcopy(property_definition)

            type_ = property_definition.get('type')

            if type_ in ('many2one', 'many2many'):
                # check if the model still exists in the environment, the module of the
                # model might have been uninstalled so the model might not exist anymore
                property_model = property_definition.get('comodel')
                if property_model not in record.env:
                    property_definition['comodel'] = False
                    property_definition.pop('domain', None)
                elif property_domain := property_definition.get('domain'):
                    # some fields in the domain might have been removed
                    # (e.g. if the module has been uninstalled)
                    # check if the domain is still valid
                    try:
                        dom = Domain(ast.literal_eval(property_domain))
                        model = record.env[property_model]
                        dom.validate(model)
                    except ValueError:
                        del property_definition['domain']

            elif type_ in ('selection', 'tags'):
                # always set at least an empty array if there's no option
                property_definition[type_] = property_definition.get(type_) or []

            result.append(property_definition)

        return result

    def convert_to_read(self, value, record, use_display_name=True):
        # record format -> read format (list of dicts with display names)
        if not value:
            return value

        if use_display_name:
            Properties._add_display_name(value, record.env, value_keys=('default',))

        return value

    def convert_to_write(self, value, record):
        return value

    def _validate_properties_definition(self, properties_definition, env):
        """Raise an error if the property definition is not valid."""
        allowed_keys = self.ALLOWED_KEYS + env["base"]._additional_allowed_keys_properties_definition()

        env["base"]._validate_properties_definition(properties_definition, self)

        properties_names = set()

        for property_definition in properties_definition:
            for property_parameter, allowed_types in self.PROPERTY_PARAMETERS_MAP.items():
                if property_definition.get('type') not in allowed_types and property_parameter in property_definition:
                    raise ValueError(f'Invalid property parameter {property_parameter!r}')

            property_definition_keys = set(property_definition.keys())

            invalid_keys = property_definition_keys - set(allowed_keys)
            if invalid_keys:
                raise ValueError(
                    'Some key are not allowed for a properties definition [%s].' %
                    ', '.join(invalid_keys),
                )

            check_property_field_value_name(property_definition['name'])

            required_keys = set(self.REQUIRED_KEYS) - property_definition_keys
            if required_keys:
                raise ValueError(
                    'Some key are missing for a properties definition [%s].' %
                    ', '.join(required_keys),
                )

            property_type = property_definition.get('type')
            property_name = property_definition.get('name')
            if not property_name or property_name in properties_names:
                raise ValueError(f'The property name {property_name!r} is not set or duplicated.')
            properties_names.add(property_name)

            if property_type == 'html' and not property_name.endswith('_html'):
                raise ValueError("HTML property name should end with `_html`.")

            if property_type != 'html' and property_name.endswith('_html'):
                raise ValueError("Only HTML properties can have the `_html` suffix.")

            if property_type and property_type not in Properties.ALLOWED_TYPES:
                raise ValueError(f'Wrong property type {property_type!r}.')

            if property_type == 'html' and (default := property_definition.get('default')):
                property_definition['default'] = html_sanitize(default, **Properties.HTML_SANITIZE_OPTIONS)

            model = property_definition.get('comodel')
            if model and (model not in env or env[model].is_transient() or env[model]._abstract):
                raise ValueError(f'Invalid model name {model!r}')

            property_selection = property_definition.get('selection')
            if property_selection:
                if (not is_list_of(property_selection, (list, tuple))
                   or not all(len(selection) == 2 for selection in property_selection)):
                    raise ValueError(f'Wrong options {property_selection!r}.')

                all_options = [option[0] for option in property_selection]
                if len(all_options) != len(set(all_options)):
                    duplicated = set(filter(lambda x: all_options.count(x) > 1, all_options))
                    raise ValueError(f'Some options are duplicated: {", ".join(duplicated)}.')

            property_tags = property_definition.get('tags')
            if property_tags:
                if (not is_list_of(property_tags, (list, tuple))
                   or not all(len(tag) == 3 and isinstance(tag[2], int) for tag in property_tags)):
                    raise ValueError(f'Wrong tags definition {property_tags!r}.')

                all_tags = [tag[0] for tag in property_tags]
                if len(all_tags) != len(set(all_tags)):
                    duplicated = set(filter(lambda x: all_tags.count(x) > 1, all_tags))
                    raise ValueError(f'Some tags are duplicated: {", ".join(duplicated)}.')
