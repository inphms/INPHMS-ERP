from __future__ import annotations
import typing as t
import logging

from collections import defaultdict

from .baserelationalmulti import _RelationalMulti
from inphms.tools import Sentinel, SENTINEL, OrderedSet
from inphms.databases import SQL, Query, sqlutils
from inphms.exceptions import AccessError
from ..numeric import NewId
from ..commands import Command
from ...utils import check_pg_name

if t.TYPE_CHECKING:
    from inphms.orm.models import BaseModel

    OnDelete = t.Literal['cascade', 'set null', 'restrict']

_schema = logging.getLogger("inphms.schema")


class Many2many(_RelationalMulti):
    """ Many2many field; the value of such a field is the recordset.

        :param str comodel_name: name of the target model (string)
            mandatory except in the case of related or extended fields

        :param str relation: optional name of the table that stores the relation in
            the database

        :param str column1: optional name of the column referring to "these" records
            in the table ``relation``

        :param str column2: optional name of the column referring to "those" records
            in the table ``relation``

        The attributes ``relation``, ``column1`` and ``column2`` are optional.
        If not given, names are automatically generated from model names,
        provided ``model_name`` and ``comodel_name`` are different!

        Note that having several fields with implicit relation parameters on a
        given model with the same comodel is not accepted by the ORM, since
        those field would use the same table. The ORM prevents two many2many
        fields to use the same relation parameters, except if

        - both fields use the same model, comodel, and relation parameters are
        explicit; or

        - at least one field belongs to a model with ``_auto = False``.

        :param domain: an optional domain to set on candidate values on the
            client side (domain or a python expression that will be evaluated
            to provide domain)

        :param dict context: an optional context to use on the client side when
            handling that field

        :param bool check_company: Mark the field to be verified in
            :meth:`~inphms.models.Model._check_company`. Add a default company
            domain depending on the field attributes.

    """
    type = 'many2many'

    _explicit: bool = True              # whether schema is explicitly given
    relation: str | None = None         # name of table
    column1: str | None = None          # column of table referring to model
    column2: str | None = None          # column of table referring to comodel
    ondelete: OnDelete | None = 'cascade'  # optional ondelete for the column2 fkey

    def __init__(self, comodel_name: str | Sentinel = SENTINEL, relation: str | Sentinel = SENTINEL,
                 column1: str | Sentinel = SENTINEL, column2: str | Sentinel = SENTINEL,
                 string: str | Sentinel = SENTINEL, **kwargs):
        super().__init__(
            comodel_name=comodel_name,
            relation=relation,
            column1=column1,
            column2=column2,
            string=string,
            **kwargs
        )

    def setup_nonrelated(self, model: BaseModel) -> None:
        super().setup_nonrelated(model)
        # 2 cases:
        # 1) The ondelete attribute is defined and its definition makes sense
        # 2) The ondelete attribute is explicitly defined as 'set null' for a m2m,
        #    this is considered a programming error.
        if self.ondelete not in ('cascade', 'restrict'):
            raise ValueError(
                "The m2m field %s of model %s declares its ondelete policy "
                "as being %r. Only 'restrict' and 'cascade' make sense."
                % (self.name, model._name, self.ondelete)
            )
        if self.store:
            if not (self.relation and self.column1 and self.column2):
                if not self.relation:
                    self._explicit = False
                # table name is based on the stable alphabetical order of tables
                comodel = model.env[self.comodel_name]
                if not self.relation:
                    tables = sorted([model._table, comodel._table])
                    assert tables[0] != tables[1], \
                        "%s: Implicit/canonical naming of many2many relationship " \
                        "table is not possible when source and destination models " \
                        "are the same" % self
                    self.relation = '%s_%s_rel' % tuple(tables)
                if not self.column1:
                    self.column1 = '%s_id' % model._table
                if not self.column2:
                    self.column2 = '%s_id' % comodel._table
            # check validity of table name
            check_pg_name(self.relation)
        else:
            self.relation = self.column1 = self.column2 = None

        if self.relation:
            # check whether other fields use the same schema
            fields = model.pool.many2many_relations[self.relation, self.column1, self.column2]
            for mname, fname in fields:
                field = model.pool[mname]._fields[fname]
                if (
                    field is self
                ) or (    # same model: relation parameters must be explicit
                    self.model_name == field.model_name and
                    self.comodel_name == field.comodel_name and
                    self._explicit and field._explicit
                ) or (  # different models: one model must be _auto=False
                    self.model_name != field.model_name and
                    not (model._auto and model.env[field.model_name]._auto)
                ):
                    continue
                msg = "Many2many fields %s and %s use the same table and columns"
                raise TypeError(msg % (self, field))
            fields.add((self.model_name, self.name))

    def setup_inverses(self, registry, inverses):
        if self.relation:
            # retrieve inverse fields, and link them in field_inverses
            for mname, fname in registry.many2many_relations[self.relation, self.column2, self.column1]:
                field = registry[mname]._fields[fname]
                inverses.add(self, field)
                inverses.add(field, self)

    def update_db(self, model, columns):
        cr = model.env.cr
        # Do not reflect relations for custom fields, as they do not belong to a
        # module. They are automatically removed when dropping the corresponding
        # 'ir.model.field'.
        if not self.manual:
            model.pool.post_init(model.env['ir.model.relation']._reflect_relation,
                                 model, self.relation, self._module)
        comodel = model.env[self.comodel_name]
        if not sqlutils.table_exists(cr, self.relation):
            cr.execute(SQL(
                """ CREATE TABLE %(rel)s (%(id1)s INTEGER NOT NULL,
                                          %(id2)s INTEGER NOT NULL,
                                          PRIMARY KEY(%(id1)s, %(id2)s));
                    COMMENT ON TABLE %(rel)s IS %(comment)s;
                    CREATE INDEX ON %(rel)s (%(id2)s, %(id1)s); """,
                rel=SQL.identifier(self.relation),
                id1=SQL.identifier(self.column1),
                id2=SQL.identifier(self.column2),
                comment=f"RELATION BETWEEN {model._table} AND {comodel._table}",
            ))
            _schema.debug("Create table %r: m2m relation between %r and %r", self.relation, model._table, comodel._table)
            model.pool.post_init(self.update_db_foreign_keys, model)
            return True

        model.pool.post_init(self.update_db_foreign_keys, model)

    def update_db_foreign_keys(self, model: BaseModel):
        """ Add the foreign keys corresponding to the field's relation table. """
        comodel = model.env[self.comodel_name]
        if model._is_an_ordinary_table():
            model.pool.add_foreign_key(
                self.relation, self.column1, model._table, 'id', 'cascade',
                model, self._module, force=False,
            )
        if comodel._is_an_ordinary_table():
            model.pool.add_foreign_key(
                self.relation, self.column2, comodel._table, 'id', self.ondelete,
                model, self._module,
            )

    def read(self, records):
        context = {'active_test': False}
        context.update(self.context)
        comodel = records.env[self.comodel_name].with_context(**context)

        # make the query for the lines
        domain = self.get_comodel_domain(records)
        try:
            query = comodel._search(domain, order=comodel._order)
        except AccessError as e:
            raise AccessError("Failed to read field %s" % self + '\n' + str(e)) from e

        # join with many2many relation table
        sql_id1 = SQL.identifier(self.relation, self.column1)
        sql_id2 = SQL.identifier(self.relation, self.column2)
        query.add_join('JOIN', self.relation, None, SQL(
            "%s = %s", sql_id2, SQL.identifier(comodel._table, 'id'),
        ))
        query.add_where(SQL("%s IN %s", sql_id1, tuple(records.ids)))

        # retrieve pairs (record, line) and group by record
        group = defaultdict(list)
        for id1, id2 in records.env.execute_query(query.select(sql_id1, sql_id2)):
            group[id1].append(id2)

        # store result in cache
        values = [tuple(group[id_]) for id_ in records._ids]
        self._insert_cache(records, values)

    def write_real(self, records_commands_list, create=False):
        # records_commands_list = [(records, commands), ...]
        if not records_commands_list:
            return

        model = records_commands_list[0][0].browse()
        comodel = model.env[self.comodel_name].with_context(**self.context)
        comodel = self._check_sudo_commands(comodel)
        cr = model.env.cr

        # determine old and new relation {x: ys}
        set = OrderedSet
        ids = set(rid for recs, cs in records_commands_list for rid in recs.ids)
        records = model.browse(ids)

        if self.store:
            # Using `record[self.name]` generates 2 SQL queries when the value
            # is not in cache: one that actually checks access rules for
            # records, and the other one fetching the actual data. We use
            # `self.read` instead to shortcut the first query.
            missing_ids = tuple(self._cache_missing_ids(records))
            if missing_ids:
                self.read(records.browse(missing_ids))

        # determine new relation {x: ys}
        old_relation = {record.id: set(record[self.name]._ids) for record in records}
        new_relation = {x: set(ys) for x, ys in old_relation.items()}

        # operations on new relation
        def relation_add(xs, y):
            for x in xs:
                new_relation[x].add(y)

        def relation_remove(xs, y):
            for x in xs:
                new_relation[x].discard(y)

        def relation_set(xs, ys):
            for x in xs:
                new_relation[x] = set(ys)

        def relation_delete(ys):
            # the pairs (x, y) have been cascade-deleted from relation
            for ys1 in old_relation.values():
                ys1 -= ys
            for ys1 in new_relation.values():
                ys1 -= ys

        for recs, commands in records_commands_list:
            to_create = []  # line vals to create
            to_delete = []  # line ids to delete
            for command in (commands or ()):
                if not isinstance(command, (list, tuple)) or not command:
                    continue
                if command[0] == Command.CREATE:
                    to_create.append((recs._ids, command[2]))
                elif command[0] == Command.UPDATE:
                    prefetch_ids = recs[self.name]._prefetch_ids
                    comodel.browse(command[1]).with_prefetch(prefetch_ids).write(command[2])
                elif command[0] == Command.DELETE:
                    to_delete.append(command[1])
                elif command[0] == Command.UNLINK:
                    relation_remove(recs._ids, command[1])
                elif command[0] == Command.LINK:
                    relation_add(recs._ids, command[1])
                elif command[0] in (Command.CLEAR, Command.SET):
                    # new lines must no longer be linked to records
                    to_create = [(set(ids) - set(recs._ids), vals) for (ids, vals) in to_create]
                    relation_set(recs._ids, command[2] if command[0] == Command.SET else ())

            if to_create:
                # create lines in batch, and link them
                lines = comodel.create([vals for ids, vals in to_create])
                for line, (ids, _vals) in zip(lines, to_create):
                    relation_add(ids, line.id)

            if to_delete:
                # delete lines in batch
                comodel.browse(to_delete).unlink()
                relation_delete(to_delete)

        # check comodel access of added records
        # we check the su flag of the environment of records, because su may be
        # disabled on the comodel
        if not model.env.su:
            try:
                comodel.browse(
                    co_id
                    for rec_id, new_co_ids in new_relation.items()
                    for co_id in new_co_ids - old_relation[rec_id]
                ).check_access('read')
            except AccessError as e:
                raise AccessError("Failed to write field %s" % self + "\n" + str(e))

        # update the cache of self
        for record in records:
            self._update_cache(record, tuple(new_relation[record.id]))

        # determine the corecords for which the relation has changed
        modified_corecord_ids = set()

        # process pairs to add (beware of duplicates)
        pairs = [(x, y) for x, ys in new_relation.items() for y in ys - old_relation[x]]
        if pairs:
            if self.store:
                cr.execute(SQL(
                    "INSERT INTO %s (%s, %s) VALUES %s ON CONFLICT DO NOTHING",
                    SQL.identifier(self.relation),
                    SQL.identifier(self.column1),
                    SQL.identifier(self.column2),
                    SQL(", ").join(pairs),
                ))

            # update the cache of inverse fields
            y_to_xs = defaultdict(set)
            for x, y in pairs:
                y_to_xs[y].add(x)
                modified_corecord_ids.add(y)
            for invf in records.pool.field_inverses[self]:
                domain = invf.get_comodel_domain(comodel)
                valid_ids = set(records.filtered_domain(domain)._ids)
                if not valid_ids:
                    continue
                inv_cache = invf._get_cache(comodel.env)
                for y, xs in y_to_xs.items():
                    corecord = comodel.browse(y)
                    try:
                        ids0 = inv_cache[corecord.id]
                        ids1 = tuple(set(ids0) | (xs & valid_ids))
                        invf._update_cache(corecord, ids1)
                    except KeyError:
                        pass

        # process pairs to remove
        pairs = [(x, y) for x, ys in old_relation.items() for y in ys - new_relation[x]]
        if pairs:
            y_to_xs = defaultdict(set)
            for x, y in pairs:
                y_to_xs[y].add(x)
                modified_corecord_ids.add(y)

            if self.store:
                # express pairs as the union of cartesian products:
                #    pairs = [(1, 11), (1, 12), (1, 13), (2, 11), (2, 12), (2, 14)]
                # -> y_to_xs = {11: {1, 2}, 12: {1, 2}, 13: {1}, 14: {2}}
                # -> xs_to_ys = {{1, 2}: {11, 12}, {2}: {14}, {1}: {13}}
                xs_to_ys = defaultdict(set)
                for y, xs in y_to_xs.items():
                    xs_to_ys[frozenset(xs)].add(y)
                # delete the rows where (id1 IN xs AND id2 IN ys) OR ...
                cr.execute(SQL(
                    "DELETE FROM %s WHERE %s",
                    SQL.identifier(self.relation),
                    SQL(" OR ").join(
                        SQL("%s IN %s AND %s IN %s",
                            SQL.identifier(self.column1), tuple(xs),
                            SQL.identifier(self.column2), tuple(ys))
                        for xs, ys in xs_to_ys.items()
                    ),
                ))

            # update the cache of inverse fields
            for invf in records.pool.field_inverses[self]:
                inv_cache = invf._get_cache(comodel.env)
                for y, xs in y_to_xs.items():
                    corecord = comodel.browse(y)
                    try:
                        ids0 = inv_cache[corecord.id]
                        ids1 = tuple(id_ for id_ in ids0 if id_ not in xs)
                        invf._update_cache(corecord, ids1)
                    except KeyError:
                        pass

        if modified_corecord_ids:
            # trigger the recomputation of fields that depend on the inverse
            # fields of self on the modified corecords
            corecords = comodel.browse(modified_corecord_ids)
            corecords.modified([
                invf.name
                for invf in model.pool.field_inverses[self]
                if invf.model_name == self.comodel_name
            ])

    def write_new(self, records_commands_list):
        """ Update self on new records. """
        if not records_commands_list:
            return

        model = records_commands_list[0][0].browse()
        comodel = model.env[self.comodel_name].with_context(**self.context)
        comodel = self._check_sudo_commands(comodel)
        new = lambda id_: id_ and NewId(id_)

        # determine old and new relation {x: ys}
        set = OrderedSet
        old_relation = {record.id: set(record[self.name]._ids) for records, _ in records_commands_list for record in records}
        new_relation = {x: set(ys) for x, ys in old_relation.items()}

        for recs, commands in records_commands_list:
            for command in commands:
                if not isinstance(command, (list, tuple)) or not command:
                    continue
                if command[0] == Command.CREATE:
                    line_id = comodel.new(command[2], ref=command[1]).id
                    for line_ids in new_relation.values():
                        line_ids.add(line_id)
                elif command[0] == Command.UPDATE:
                    line_id = new(command[1])
                    comodel.browse([line_id]).update(command[2])
                elif command[0] == Command.DELETE:
                    line_id = new(command[1])
                    for line_ids in new_relation.values():
                        line_ids.discard(line_id)
                elif command[0] == Command.UNLINK:
                    line_id = new(command[1])
                    for line_ids in new_relation.values():
                        line_ids.discard(line_id)
                elif command[0] == Command.LINK:
                    line_id = new(command[1])
                    for line_ids in new_relation.values():
                        line_ids.add(line_id)
                elif command[0] in (Command.CLEAR, Command.SET):
                    # new lines must no longer be linked to records
                    line_ids = command[2] if command[0] == Command.SET else ()
                    line_ids = set(new(line_id) for line_id in line_ids)
                    for id_ in recs._ids:
                        new_relation[id_] = set(line_ids)

        if new_relation == old_relation:
            return

        records = model.browse(old_relation)

        # update the cache of self
        for record in records:
            self._update_cache(record, tuple(new_relation[record.id]))

        # determine the corecords for which the relation has changed
        modified_corecord_ids = set()

        # process pairs to add (beware of duplicates)
        pairs = [(x, y) for x, ys in new_relation.items() for y in ys - old_relation[x]]
        if pairs:
            # update the cache of inverse fields
            y_to_xs = defaultdict(set)
            for x, y in pairs:
                y_to_xs[y].add(x)
                modified_corecord_ids.add(y)
            for invf in records.pool.field_inverses[self]:
                domain = invf.get_comodel_domain(comodel)
                valid_ids = set(records.filtered_domain(domain)._ids)
                if not valid_ids:
                    continue
                inv_cache = invf._get_cache(comodel.env)
                for y, xs in y_to_xs.items():
                    corecord = comodel.browse((y,))
                    try:
                        ids0 = inv_cache[corecord.id]
                        ids1 = tuple(set(ids0) | (xs & valid_ids))
                        invf._update_cache(corecord, ids1)
                    except KeyError:
                        pass

        # process pairs to remove
        pairs = [(x, y) for x, ys in old_relation.items() for y in ys - new_relation[x]]
        if pairs:
            # update the cache of inverse fields
            y_to_xs = defaultdict(set)
            for x, y in pairs:
                y_to_xs[y].add(x)
                modified_corecord_ids.add(y)
            for invf in records.pool.field_inverses[self]:
                inv_cache = invf._get_cache(comodel.env)
                for y, xs in y_to_xs.items():
                    corecord = comodel.browse((y,))
                    try:
                        ids0 = inv_cache[corecord.id]
                        ids1 = tuple(id_ for id_ in ids0 if id_ not in xs)
                        invf._update_cache(corecord, ids1)
                    except KeyError:
                        pass

        if modified_corecord_ids:
            # trigger the recomputation of fields that depend on the inverse
            # fields of self on the modified corecords
            corecords = comodel.browse(modified_corecord_ids)
            corecords.modified([
                invf.name
                for invf in model.pool.field_inverses[self]
                if invf.model_name == self.comodel_name
            ])

    def _condition_to_sql_relational(self, model: BaseModel, alias: str, exists: bool, coquery: Query, query: Query) -> SQL:
        if coquery.is_empty():
            return SQL("FALSE") if exists else SQL("TRUE")
        rel_table, rel_id1, rel_id2 = self.relation, self.column1, self.column2
        rel_alias = query.make_alias(alias, self.name)
        if not coquery.where_clause:
            # case: no constraints on table and we have foreign keys
            # so we can inverse the operator and check existence
            exists = not exists
            return SQL(
                "%sEXISTS (SELECT 1 FROM %s AS %s WHERE %s = %s)",
                SQL("NOT ") if exists else SQL(),
                SQL.identifier(rel_table),
                SQL.identifier(rel_alias),
                SQL.identifier(rel_alias, rel_id1),
                SQL.identifier(alias, 'id'),
            )
        return SQL(
            "%sEXISTS (SELECT 1 FROM %s AS %s WHERE %s = %s AND %s IN %s)",
            SQL("NOT ") if not exists else SQL(),
            SQL.identifier(rel_table),
            SQL.identifier(rel_alias),
            SQL.identifier(rel_alias, rel_id1),
            SQL.identifier(alias, 'id'),
            SQL.identifier(rel_alias, rel_id2),
            coquery.subselect(),
        )
