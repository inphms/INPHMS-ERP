from __future__ import annotations
import logging
import typing as t

from pprint import pformat

from .utils import EMPTY_DICT
from inphms.tools import SENTINEL, OrderedSet
from inphms.exceptions import CacheMiss
from inphms.databases import SQL, Query

if t.TYPE_CHECKING:
    from .transactions import Transaction
    from .environments import Environment
    from inphms.orm.fields import Field, IdType
    from inphms.orm.models import BaseModel
    from collections.abc import Iterable, Iterator, Mapping, Collection

_logger = logging.getLogger("inphms.api")


class Cache:
    """ Implementation of the cache of records.

        For most fields, the cache is simply a mapping from a record and a field to
        a value.  In the case of context-dependent fields, the mapping also depends
        on the environment of the given record.  For the sake of performance, the
        cache is first partitioned by field, then by record.  This makes some
        common ORM operations pretty fast, like determining which records have a
        value for a given field, or invalidating a given field on all possible
        records.

        The cache can also mark some entries as "dirty".  Dirty entries essentially
        marks values that are different from the database.  They represent database
        updates that haven't been done yet.  Note that dirty entries only make
        sense for stored fields.  Note also that if a field is dirty on a given
        record, and the field is context-dependent, then all the values of the
        record for that field are considered dirty.  For the sake of consistency,
        the values that should be in the database must be in a context where all
        the field's context keys are ``None``.
    """
    __slots__ = ('transaction',)

    def __init__(self, transaction: Transaction):
        self.transaction = transaction

    def __repr__(self) -> str:
        # for debugging: show the cache content and dirty flags as stars
        data: dict[Field, dict] = {}
        for field, field_cache in sorted(self.transaction.field_data.items(), key=lambda item: str(item[0])):
            dirty_ids = self.transaction.field_dirty.get(field, ())
            if field in self.transaction.registry.field_depends_context:
                data[field] = {
                    key: {
                        Starred(id_) if id_ in dirty_ids else id_: val if field.type != 'binary' else '<binary>'
                        for id_, val in key_cache.items()
                    }
                    for key, key_cache in field_cache.items()
                }
            else:
                data[field] = {
                    Starred(id_) if id_ in dirty_ids else id_: val if field.type != 'binary' else '<binary>'
                    for id_, val in field_cache.items()
                }
        return repr(data)

    def _get_field_cache(self, model: BaseModel, field: Field) -> Mapping[IdType, t.Any]:
        """ Return the field cache of the given field, but not for modifying it. """
        return self._set_field_cache(model, field)

    def _set_field_cache(self, model: BaseModel, field: Field) -> dict[IdType, t.Any]:
        """ Return the field cache of the given field for modifying it. """
        return field._get_cache(model.env)

    def contains(self, record: BaseModel, field: Field) -> bool:
        """ Return whether ``record`` has a value for ``field``. """
        return record.id in self._get_field_cache(record, field)

    def contains_field(self, field: Field) -> bool:
        """ Return whether ``field`` has a value for at least one record. """
        cache = self.transaction.field_data.get(field)
        if not cache:
            return False
        # 'cache' keys are tuples if 'field' is context-dependent, record ids otherwise
        if field in self.transaction.registry.field_depends_context:
            return any(value for value in cache.values())
        return True

    def get(self, record: BaseModel, field: Field, default=SENTINEL):
        """ Return the value of ``field`` for ``record``. """
        try:
            field_cache = self._get_field_cache(record, field)
            return field_cache[record._ids[0]]
        except KeyError:
            if default is SENTINEL:
                raise CacheMiss(record, field) from None
            return default

    def set(self, record: BaseModel, field: Field, value: t.Any, dirty: bool = False) -> None:
        """ Set the value of ``field`` for ``record``.
            One can normally make a clean field dirty but not the other way around.
            Updating a dirty field without ``dirty=True`` is a programming error and
            raises an exception.

            :param dirty: whether ``field`` must be made dirty on ``record`` after
                the update
        """
        field._update_cache(record, value, dirty=dirty)

    def update(self, records: BaseModel, field: Field, values: Iterable, dirty: bool = False) -> None:
        """ Set the values of ``field`` for several ``records``.
            One can normally make a clean field dirty but not the other way around.
            Updating a dirty field without ``dirty=True`` is a programming error and
            raises an exception.

            :param dirty: whether ``field`` must be made dirty on ``record`` after
                the update
        """
        for record, value in zip(records, values):
            field._update_cache(record, value, dirty=dirty)

    def update_raw(self, records: BaseModel, field: Field, values: Iterable, dirty: bool = False) -> None:
        """ This is a variant of method :meth:`~update` without the logic for
            translated fields.
        """
        if field.translate:
            records = records.with_context(prefetch_langs=True)
        for record, value in zip(records, values):
            field._update_cache(record, value, dirty=dirty)

    def remove(self, record: BaseModel, field: Field) -> None:
        """ Remove the value of ``field`` for ``record``. """
        assert record.id not in self.transaction.field_dirty.get(field, ())
        try:
            field_cache = self._set_field_cache(record, field)
            del field_cache[record._ids[0]]
        except KeyError:
            pass

    def get_values(self, records: BaseModel, field: Field) -> Iterator[t.Any]:
        """ Return the cached values of ``field`` for ``records``. """
        field_cache = self._get_field_cache(records, field)
        for record_id in records._ids:
            try:
                yield field_cache[record_id]
            except KeyError:
                pass

    def get_fields(self, record: BaseModel) -> Iterator[Field]:
        """ Return the fields with a value for ``record``. """
        for name, field in record._fields.items():
            if name != 'id' and record.id in self._get_field_cache(record, field):
                yield field

    def get_records(self, model: BaseModel, field: Field, all_contexts: bool = False) -> BaseModel:
        """ Return the records of ``model`` that have a value for ``field``.
            By default the method checks for values in the current context of ``model``.
            But when ``all_contexts`` is true, it checks for values *in all contexts*.
        """
        ids: Iterable
        if all_contexts and field in model.pool.field_depends_context:
            field_cache = self.transaction.field_data.get(field, EMPTY_DICT)
            ids = OrderedSet(id_ for sub_cache in field_cache.values() for id_ in sub_cache)
        else:
            ids = self._get_field_cache(model, field)
        return model.browse(ids)

    def get_missing_ids(self, records: BaseModel, field: Field) -> Iterator[IdType]:
        """ Return the ids of ``records`` that have no value for ``field``. """
        return field._cache_missing_ids(records)

    def invalidate(self, spec: Collection[tuple[Field, Collection[IdType] | None]] | None = None) -> None:
        """ Invalidate the cache, partially or totally depending on ``spec``.

            If a field is context-dependent, invalidating it for a given record
            actually invalidates all the values of that field on the record.  In
            other words, the field is invalidated for the record in all
            environments.

            This operation is unsafe by default, and must be used with care.
            Indeed, invalidating a dirty field on a record may lead to an error,
            because doing so drops the value to be written in database.

                spec = [(field, ids), (field, None), ...]
        """
        if spec is None:
            self.transaction.invalidate_field_data()
            return
        env = next(iter(self.transaction.envs))
        for field, ids in spec:
            field._invalidate_cache(env, ids)

    def clear(self):
        """ Invalidate the cache and its dirty flags. """
        self.transaction.invalidate_field_data()
        self.transaction.field_dirty.clear()
        self.transaction.field_data_patches.clear()

    def check(self, env: Environment) -> None:
        """ Check the consistency of the cache for the given environment. """
        depends_context = env.registry.field_depends_context
        invalids = []

        def process(model: BaseModel, field: Field, field_cache):
            # ignore new records and records to flush
            dirty_ids = self.transaction.field_dirty.get(field, ())
            ids = [id_ for id_ in field_cache if id_ and id_ not in dirty_ids]
            if not ids:
                return

            # select the column for the given ids
            query = Query(env, model._table, model._table_sql)
            sql_id = SQL.identifier(model._table, 'id')
            sql_field = model._field_to_sql(model._table, field.name, query)
            if field.type == 'binary' and (
                model.env.context.get('bin_size') or model.env.context.get('bin_size_' + field.name)
            ):
                sql_field = SQL('pg_size_pretty(length(%s)::bigint)', sql_field)
            query.add_where(SQL("%s IN %s", sql_id, tuple(ids)))
            env.cr.execute(query.select(sql_id, sql_field))

            # compare returned values with corresponding values in cache
            for id_, value in env.cr.fetchall():
                cached = field_cache[id_]
                if value == cached or (not value and not cached):
                    continue
                invalids.append((model.browse((id_,)), field, {'cached': cached, 'fetched': value}))

        for field, field_cache in self.transaction.field_data.items():
            # check column fields only
            if not field.store or not field.column_type or field.translate or field.company_dependent:
                continue

            model = env[field.model_name]
            if field in depends_context:
                for context_keys, inner_cache in field_cache.items():
                    context = dict[str, t.Any](zip(depends_context[field], context_keys))
                    if 'company' in context:
                        # the cache key 'company' actually comes from context
                        # key 'allowed_company_ids' (see property env.company
                        # and method env.cache_key())
                        context['allowed_company_ids'] = [context.pop('company')]
                    process(model.with_context(context), field, inner_cache)
            else:
                process(model, field, field_cache)

        if invalids:
            _logger.warning("Invalid cache: %s", pformat(invalids))


class Starred:
    """ Simple helper class to ``repr`` a value with a star suffix. """
    __slots__ = ['value']

    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"{self.value!r}*"
