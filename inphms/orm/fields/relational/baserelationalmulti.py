from __future__ import annotations
import typing as t
import itertools

from .baserelational import _Relational
from inphms.tools import SENTINEL, unique, OrderedSet
from inphms.orm.domains import Domain
from inphms.databases import SQL, Query
from ..numeric import NewId
from ..commands import Command
from .utils import PrefetchX2many
from ..utils import COLLECTION_TYPES

if t.TYPE_CHECKING:
    from collections.abc import Sequence
    from ...types import CommandValue
    from inphms.orm.models import BaseModel

    OnDelete = t.Literal['cascade', 'set null', 'restrict']


class _RelationalMulti(_Relational):
    r"Abstract class for relational fields \*2many."
    write_sequence = 20

    # Important: the cache contains the ids of all the records in the relation,
    # including inactive records.  Inactive records are filtered out by
    # convert_to_record(), depending on the context.

    def _update_inverse(self, records, value):
        new_id = value.id
        assert not new_id, "Field._update_inverse can only be called with a new id"
        field_cache = self._get_cache(records.env)
        for record_id in records._ids:
            assert not record_id, "Field._update_inverse can only be called with new records"
            cache_value = field_cache.get(record_id, SENTINEL)
            if cache_value is SENTINEL:
                records.env.transaction.field_data_patches[self][record_id].append(new_id)
            else:
                field_cache[record_id] = tuple(unique(cache_value + (new_id,)))

    def _update_cache(self, records, cache_value, dirty=False):
        field_patches = records.env.transaction.field_data_patches.get(self)
        if field_patches and records:
            for record in records:
                ids = field_patches.pop(record.id, ())
                if ids:
                    value = tuple(unique(itertools.chain(cache_value, ids)))
                else:
                    value = cache_value
                super()._update_cache(record, value, dirty)
            return
        super()._update_cache(records, cache_value, dirty)

    def convert_to_cache(self, value, record: BaseModel, validate=True):
        # cache format: tuple(ids)
        from inphms.orm.models import BaseModel
        if isinstance(value, BaseModel):
            if validate and value._name != self.comodel_name:
                raise ValueError("Wrong value for %s: %s" % (self, value))
            ids = value._ids
            if record and not record.id:
                # x2many field value of new record is new records
                ids = tuple(it and NewId(it) for it in ids)
            return ids

        elif isinstance(value, (list, tuple)):
            # value is a list/tuple of commands, dicts or record ids
            comodel = record.env[self.comodel_name]
            # if record is new, the field's value is new records
            if record and not record.id:
                browse = lambda it: comodel.browse((it and NewId(it),))
            else:
                browse = comodel.browse
            # determine the value ids: in case of a real record or a new record
            # with origin, take its current value
            ids = OrderedSet(record[self.name]._ids if record._origin else ())
            # modify ids with the commands
            for command in value:
                if isinstance(command, (tuple, list)):
                    if command[0] == Command.CREATE:
                        ids.add(comodel.new(command[2], ref=command[1]).id)
                    elif command[0] == Command.UPDATE:
                        line = browse(command[1])
                        if validate:
                            line.update(command[2])
                        else:
                            line._update_cache(command[2], validate=False)
                        ids.add(line.id)
                    elif command[0] in (Command.DELETE, Command.UNLINK):
                        ids.discard(browse(command[1]).id)
                    elif command[0] == Command.LINK:
                        ids.add(browse(command[1]).id)
                    elif command[0] == Command.CLEAR:
                        ids.clear()
                    elif command[0] == Command.SET:
                        ids = OrderedSet(browse(it).id for it in command[2])
                elif isinstance(command, dict):
                    ids.add(comodel.new(command).id)
                else:
                    ids.add(browse(command).id)
            # return result as a tuple
            return tuple(ids)

        elif not value:
            return ()

        raise ValueError("Wrong value for %s: %s" % (self, value))

    def convert_to_record(self, value, record: BaseModel):
        # use registry to avoid creating a recordset for the model
        prefetch_ids = PrefetchX2many(record, self)
        Comodel = record.pool[self.comodel_name]
        corecords = Comodel(record.env, value, prefetch_ids)
        if (
            Comodel._active_name
            and self.context.get('active_test', record.env.context.get('active_test', True))
        ):
            corecords = corecords.filtered(Comodel._active_name).with_prefetch(prefetch_ids)
        return corecords

    def convert_to_record_multi(self, values, records: BaseModel):
        # return the list of ids as a recordset without duplicates
        prefetch_ids = PrefetchX2many(records, self)
        Comodel = records.pool[self.comodel_name]
        ids = tuple(unique(id_ for ids in values for id_ in ids))
        corecords = Comodel(records.env, ids, prefetch_ids)
        if (
            Comodel._active_name
            and self.context.get('active_test', records.env.context.get('active_test', True))
        ):
            corecords = corecords.filtered(Comodel._active_name).with_prefetch(prefetch_ids)
        return corecords

    def convert_to_read(self, value, record, use_display_name=True):
        return value.ids

    def convert_to_write(self, value, record: BaseModel):
        if isinstance(value, tuple):
            # a tuple of ids, this is the cache format
            value = record.env[self.comodel_name].browse(value)
        from inphms.orm.models import BaseModel
        if isinstance(value, BaseModel) and value._name == self.comodel_name:
            def get_origin(val):
                return val._origin if isinstance(val, BaseModel) else val

            # make result with new and existing records
            inv_names = {field.name for field in record.pool.field_inverses[self]}
            result = [Command.set([])]
            for record in value:
                origin = record._origin
                if not origin:
                    values = record._convert_to_write({
                        name: record[name]
                        for name in record._cache
                        if name not in inv_names
                    })
                    result.append(Command.create(values))
                else:
                    result[0][2].append(origin.id)
                    if record != origin:
                        values = record._convert_to_write({
                            name: record[name]
                            for name in record._cache
                            if name not in inv_names and get_origin(record[name]) != origin[name]
                        })
                        if values:
                            result.append(Command.update(origin.id, values))
            return result

        if value is False or value is None:
            return [Command.clear()]

        if isinstance(value, list):
            return value

        raise ValueError("Wrong value for %s: %s" % (self, value))

    def convert_to_export(self, value, record):
        return ','.join(value.mapped('display_name')) if value else ''

    def convert_to_display_name(self, value, record):
        raise NotImplementedError()

    def get_depends(self, model):
        depends, depends_context = super().get_depends(model)
        if not self.compute and isinstance(domain := self.domain, (list, Domain)):
            domain = Domain(domain)
            depends = unique(itertools.chain(depends, (
                self.name + '.' + condition.field_expr
                for condition in domain.iter_conditions()
            )))
        return depends, depends_context

    def create(self, record_values):
        """ Write the value of ``self`` on the given records, which have just
        been created.

        :param record_values: a list of pairs ``(record, value)``, where
            ``value`` is in the format of method :meth:`BaseModel.write`
        """
        self.write_batch(record_values, True)

    def write(self, records, value):
        # discard recomputation of self on records
        records.env.remove_to_compute(self, records)
        self.write_batch([(records, value)])

    def write_batch(self, records_commands_list: Sequence[tuple[BaseModel, t.Any]], create: bool = False) -> None:
        if not records_commands_list:
            return
        from inphms.orm.models import BaseModel
        for idx, (recs, value) in enumerate(records_commands_list):
            if isinstance(value, tuple):
                value = [Command.set(value)]
            elif isinstance(value, BaseModel) and value._name == self.comodel_name:
                value = [Command.set(value._ids)]
            elif value is False or value is None:
                value = [Command.clear()]
            elif isinstance(value, list) and value and not isinstance(value[0], (tuple, list)):
                value = [Command.set(tuple(value))]
            if not isinstance(value, list):
                raise ValueError("Wrong value for %s: %s" % (self, value))
            records_commands_list[idx] = (recs, value)

        record_ids = {rid for recs, cs in records_commands_list for rid in recs._ids}
        if all(record_ids):
            self.write_real(records_commands_list, create)
        else:
            assert not any(record_ids), f"{records_commands_list} contains a mix of real and new records. It is not supported."
            self.write_new(records_commands_list)

    def write_real(self, records_commands_list: Sequence[tuple[BaseModel, list[CommandValue]]], create: bool = False) -> None:
        raise NotImplementedError

    def write_new(self, records_commands_list: Sequence[tuple[BaseModel, list[CommandValue]]]) -> None:
        raise NotImplementedError

    def _check_sudo_commands(self, comodel: BaseModel):
        # if the model doesn't accept sudo commands
        if not comodel._allow_sudo_commands:
            # Then, disable sudo and reset the transaction origin user
            return comodel.sudo(False).with_user(comodel.env.transaction.default_env.uid)
        return comodel

    def condition_to_sql(self, field_expr: str, operator: str, value, model: BaseModel, alias: str, query: Query) -> SQL:
        assert field_expr == self.name, "Supporting condition only to field"
        comodel = model.env[self.comodel_name]
        if not self.store:
            raise ValueError(f"Cannot convert {self} to SQL because it is not stored")

        # update the operator to 'any'
        if operator in ('in', 'not in'):
            operator = 'any' if operator == 'in' else 'not any'
        assert operator in ('any', 'not any', 'any!', 'not any!'), \
            f"Relational field {self} expects 'any' operator"
        exists = operator in ('any', 'any!')

        # check the value and execute the query
        if isinstance(value, COLLECTION_TYPES):
            value = OrderedSet(value)
            comodel = comodel.sudo().with_context(active_test=False)
            if False in value:
                #  [not]in (False, 1) => split conditions
                #  We want records that have a record such as condition or
                #  that don't have any records.
                if len(value) > 1:
                    in_operator = 'in' if exists else 'not in'
                    return SQL(
                        "(%s OR %s)" if exists else "(%s AND %s)",
                        self.condition_to_sql(field_expr, in_operator, (False,), model, alias, query),
                        self.condition_to_sql(field_expr, in_operator, value - {False}, model, alias, query),
                    )
                #  in (False) => not any (Domain.TRUE)
                #  not in (False) => any (Domain.TRUE)
                value = comodel._search(Domain.TRUE)
                exists = not exists
            else:
                value = comodel.browse(value)._as_query(ordered=False)
        elif isinstance(value, SQL):
            # wrap SQL into a simple query
            comodel = comodel.sudo()
            value = Domain('id', 'any', value)
        coquery = self._get_query_for_condition_value(model, comodel, operator, value)
        return self._condition_to_sql_relational(model, alias, exists, coquery, query)

    def _get_query_for_condition_value(self, model: BaseModel, comodel: BaseModel, operator: str, value: Domain | Query) -> Query:
        """ Return Query run on the comodel with the field.domain injected."""
        field_domain = self.get_comodel_domain(model)
        if isinstance(value, Domain):
            domain = value & field_domain
            comodel = comodel.with_context(**self.context)
            bypass_access = self.bypass_search_access or operator in ('any!', 'not any!')
            query = comodel._search(domain, bypass_access=bypass_access)
            assert isinstance(query, Query)
            return query
        if isinstance(value, Query):
            # add the field_domain to the query
            domain = field_domain.optimize_full(comodel)
            if not domain.is_true():
                # TODO should clone/copy Query value
                value.add_where(domain._to_sql(comodel, value.table, value))
            return value
        raise NotImplementedError(f"Cannot build query for {value}")

    def _condition_to_sql_relational(self, model: BaseModel, alias: str, exists: bool, coquery: Query, query: Query) -> SQL:
        raise NotImplementedError

