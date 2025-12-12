from __future__ import annotations
import typing as t

from .baserelational import _Relational
from inphms.tools import Sentinel, SENTINEL, unique
from inphms.exceptions import MissingError
from inphms.orm.utils import IR_MODELS

from inphms.orm.domains import Domain
from inphms.databases import SQL, Query
from ..numeric import NewId
from .utils import PrefetchMany2one

if t.TYPE_CHECKING:
    from inphms.orm.models import BaseModel

    OnDelete = t.Literal['cascade', 'set null', 'restrict']

class Many2one(_Relational):
    """ The value of such a field is a recordset of size 0 (no
        record) or 1 (a single record).

        :param str comodel_name: name of the target model
            ``Mandatory`` except for related or extended fields.

        :param domain: an optional domain to set on candidate values on the
            client side (domain or a python expression that will be evaluated
            to provide domain)

        :param dict context: an optional context to use on the client side when
            handling that field

        :param str ondelete: what to do when the referred record is deleted;
            possible values are: ``'set null'``, ``'restrict'``, ``'cascade'``

        :param bool bypass_search_access: whether access rights are bypassed on the
            comodel (default: ``False``)

        :param bool delegate: set it to ``True`` to make fields of the target model
            accessible from the current model (corresponds to ``_inherits``)

        :param bool check_company: Mark the field to be verified in
            :meth:`~inphms.models.Model._check_company`. Has a different behaviour
            depending on whether the field is company_dependent or not.
            Constrains non-company-dependent fields to target records whose
            company_id(s) are compatible with the record's company_id(s).
            Constrains company_dependent fields to target records whose
            company_id(s) are compatible with the currently active company.
    """
    type = 'many2one'
    _column_type = ('int4', 'int4')

    ondelete: OnDelete | None = None    # what to do when value is deleted
    delegate: bool = False              # whether self implements delegation

    def __init__(self, comodel_name: str | Sentinel = SENTINEL, string: str | Sentinel = SENTINEL, **kwargs):
        super().__init__(comodel_name=comodel_name, string=string, **kwargs)

    def _setup_attrs__(self, model_class, name):
        super()._setup_attrs__(model_class, name)
        # determine self.delegate
        if name in model_class._inherits.values():
            self.delegate = True
            # self.delegate implies self.bypass_search_access
            self.bypass_search_access = True
        elif self.delegate:
            comodel_name = self.comodel_name or 'comodel_name'
            raise TypeError((
                f"The delegate field {self} must be declared in the model class e.g.\n"
                f"_inherits = {{{comodel_name!r}: {name!r}}}"
            ))

    def setup_nonrelated(self, model):
        super().setup_nonrelated(model)
        # 3 cases:
        # 1) The ondelete attribute is not defined, we assign it a sensible default
        # 2) The ondelete attribute is defined and its definition makes sense
        # 3) The ondelete attribute is explicitly defined as 'set null' for a required m2o,
        #    this is considered a programming error.
        if not self.ondelete:
            comodel = model.env[self.comodel_name]
            if model.is_transient() and not comodel.is_transient():
                # Many2one relations from TransientModel Model are annoying because
                # they can block deletion due to foreign keys. So unless stated
                # otherwise, we default them to ondelete='cascade'.
                self.ondelete = 'cascade' if self.required else 'set null'
            else:
                self.ondelete = 'restrict' if self.required else 'set null'
        if self.ondelete == 'set null' and self.required:
            raise ValueError(
                "The m2o field %s of model %s is required but declares its ondelete policy "
                "as being 'set null'. Only 'restrict' and 'cascade' make sense."
                % (self.name, model._name)
            )
        if self.ondelete == 'restrict' and self.comodel_name in IR_MODELS:
            raise ValueError(
                f"Field {self.name} of model {model._name} is defined as ondelete='restrict' "
                f"while having {self.comodel_name} as comodel, the 'restrict' mode is not "
                f"supported for this type of field as comodel."
            )

    def update_db(self, model, columns):
        comodel = model.env[self.comodel_name]
        if not model.is_transient() and comodel.is_transient():
            raise ValueError('Many2one %s from Model to TransientModel is forbidden' % self)
        return super().update_db(model, columns)

    def update_db_column(self, model, column):
        super().update_db_column(model, column)
        model.pool.post_init(self.update_db_foreign_key, model, column)

    def update_db_foreign_key(self, model: BaseModel, column):
        if self.company_dependent:
            return
        comodel = model.env[self.comodel_name]
        # foreign keys do not work on views, and users can define custom models on sql views.
        if not model._is_an_ordinary_table() or not comodel._is_an_ordinary_table():
            return
        # ir_actions is inherited, so foreign key doesn't work on it
        if not comodel._auto or comodel._table == 'ir_actions':
            return
        # create/update the foreign key, and reflect it in 'ir.model.constraint'
        model.pool.add_foreign_key(
            model._table, self.name, comodel._table, 'id', self.ondelete or 'set null',
            model, self._module
        )

    def _update_inverse(self, records, value):
        for record in records:
            self._update_cache(record, self.convert_to_cache(value, record, validate=False))

    def convert_to_column(self, value, record, values=None, validate=True):
        return value or None

    def convert_to_cache(self, value, record: BaseModel, validate=True):
        # cache format: id or None
        from inphms.orm.models import BaseModel
        if type(value) is int or type(value) is NewId:
            id_ = value
        elif isinstance(value, BaseModel):
            if validate and (value._name != self.comodel_name or len(value) > 1):
                raise ValueError("Wrong value for %s: %r" % (self, value))
            id_ = value._ids[0] if value._ids else None
        elif isinstance(value, tuple):
            # value is either a pair (id, name), or a tuple of ids
            id_ = value[0] if value else None
        elif isinstance(value, dict):
            # return a new record (with the given field 'id' as origin)
            comodel = record.env[self.comodel_name]
            origin = comodel.browse(value.get('id'))
            id_ = comodel.new(value, origin=origin).id
        else:
            id_ = None

        if self.delegate and record and not any(record._ids):
            # if all records are new, then so is the parent
            id_ = id_ and NewId(id_)

        return id_

    def convert_to_record(self, value, record):
        # use registry to avoid creating a recordset for the model
        ids = () if value is None else (value,)
        prefetch_ids = PrefetchMany2one(record, self)
        return record.pool[self.comodel_name](record.env, ids, prefetch_ids)

    def convert_to_record_multi(self, values, records):
        # return the ids as a recordset without duplicates
        prefetch_ids = PrefetchMany2one(records, self)
        ids = tuple(unique(id_ for id_ in values if id_ is not None))
        return records.pool[self.comodel_name](records.env, ids, prefetch_ids)

    def convert_to_read(self, value, record, use_display_name=True):
        if use_display_name and value:
            # evaluate display_name as superuser, because the visibility of a
            # many2one field value (id and name) depends on the current record's
            # access rights, and not the value's access rights.
            try:
                # performance: value.sudo() prefetches the same records as value
                return (value.id, value.sudo().display_name)
            except MissingError:
                # Should not happen, unless the foreign key is missing.
                return False
        else:
            return value.id

    def convert_to_write(self, value, record):
        if type(value) is int or type(value) is NewId:
            return value
        if not value:
            return False
        from inphms.orm.models import BaseModel
        if isinstance(value, BaseModel) and value._name == self.comodel_name:
            return value.id
        if isinstance(value, tuple):
            # value is either a pair (id, name), or a tuple of ids
            return value[0] if value else False
        if isinstance(value, dict):
            return record.env[self.comodel_name].new(value).id
        raise ValueError("Wrong value for %s: %r" % (self, value))

    def convert_to_export(self, value, record):
        return value.display_name if value else ''

    def convert_to_display_name(self, value, record):
        return value.display_name

    def write(self, records, value):
        # discard recomputation of self on records
        records.env.remove_to_compute(self, records)

        # discard the records that are not modified
        cache_value = self.convert_to_cache(value, records)
        records = self._filter_not_equal(records, cache_value)
        if not records:
            return

        # remove records from the cache of one2many fields of old corecords
        self._remove_inverses(records, cache_value)

        # update the cache of self
        self._update_cache(records, cache_value, dirty=True)

        # update the cache of one2many fields of new corecord
        self._update_inverses(records, cache_value)

    def _remove_inverses(self, records: BaseModel, value):
        """ Remove `records` from the cached values of the inverse fields (o2m) of `self`. """
        inverse_fields = records.pool.field_inverses[self]
        if not inverse_fields:
            return

        record_ids = set(records._ids)
        # align(id) returns a NewId if records are new, a real id otherwise
        align = (lambda id_: id_) if all(record_ids) else (lambda id_: id_ and NewId(id_))
        field_cache = self._get_cache(records.env)
        corecords = records.env[self.comodel_name].browse(
            align(coid) for record_id in records._ids
            if (coid := field_cache.get(record_id)) is not None
        )

        for invf in inverse_fields:
            inv_cache = invf._get_cache(corecords.env)
            for corecord in corecords:
                ids0 = inv_cache.get(corecord.id)
                if ids0 is not None:
                    ids1 = tuple(id_ for id_ in ids0 if id_ not in record_ids)
                    invf._update_cache(corecord, ids1)

    def _update_inverses(self, records: BaseModel, value):
        """ Add `records` to the cached values of the inverse fields (o2m) of `self`. """
        if value is None:
            return
        corecord = self.convert_to_record(value, records)
        for invf in records.pool.field_inverses[self]:
            valid_records = records.filtered_domain(invf.get_comodel_domain(corecord))
            if not valid_records:
                continue
            ids0 = invf._get_cache(corecord.env).get(corecord.id)
            # if the value for the corecord is not in cache, but this is a new
            # record, assign it anyway, as you won't be able to fetch it from
            # database (see `test_sale_order`)
            if ids0 is not None or not corecord.id:
                ids1 = tuple(unique((ids0 or ()) + valid_records._ids))
                invf._update_cache(corecord, ids1)

    def to_sql(self, model: BaseModel, alias: str) -> SQL:
        sql_field = super().to_sql(model, alias)
        if self.company_dependent:
            comodel = model.env[self.comodel_name]
            sql_field = SQL(
                '''(SELECT %(cotable_alias)s.id
                    FROM %(cotable)s AS %(cotable_alias)s
                    WHERE %(cotable_alias)s.id = %(ref)s)''',
                cotable=SQL.identifier(comodel._table),
                cotable_alias=SQL.identifier(Query.make_alias(comodel._table, 'exists')),
                ref=sql_field,
            )
        return sql_field

    def condition_to_sql(self, field_expr: str, operator: str, value, model: BaseModel, alias: str, query: Query) -> SQL:
        if operator not in ('any', 'not any', 'any!', 'not any!') or field_expr != self.name:
            # for other operators than 'any', just generate condition based on column type
            return super().condition_to_sql(field_expr, operator, value, model, alias, query)

        comodel = model.env[self.comodel_name]
        sql_field = model._field_to_sql(alias, field_expr, query)
        can_be_null = self not in model.env.registry.not_null_fields
        bypass_access = operator in ('any!', 'not any!') or self.bypass_search_access
        positive = operator in ('any', 'any!')

        # Decide whether to use a LEFT JOIN
        left_join = bypass_access and isinstance(value, Domain)
        if left_join and not positive:
            # For 'not any!', we get a better query with a NOT IN when we have a
            # lot of positive conditions which have a better chance to use
            # indexes.
            #   `field NOT IN (SELECT ... WHERE z = y)` better than
            #   `LEFT JOIN ... ON field = id WHERE z <> y`
            # There are some exceptions: we filter on 'id'.
            left_join = sum(
                (-1 if cond.operator in Domain.NEGATIVE_OPERATORS else 1)
                for cond in value.iter_conditions()
            ) < 0 or any(
                cond.field_expr == 'id' and cond.operator not in Domain.NEGATIVE_OPERATORS
                for cond in value.iter_conditions()
            )

        if left_join:
            comodel, coalias = self.join(model, alias, query)
            if not positive:
                value = (~value).optimize_full(comodel)
            sql = value._to_sql(comodel, coalias, query)
            if self.company_dependent:
                sql = self._condition_to_sql_company(sql, field_expr, operator, value, model, alias, query)
            if can_be_null:
                if positive:
                    sql = SQL("(%s IS NOT NULL AND %s)", sql_field, sql)
                else:
                    sql = SQL("(%s IS NULL OR %s)", sql_field, sql)
            return sql

        if isinstance(value, Domain):
            value = comodel._search(value, active_test=False, bypass_access=bypass_access)
        if isinstance(value, Query):
            subselect = value.subselect()
        elif isinstance(value, SQL):
            subselect = SQL("(%s)", value)
        else:
            raise TypeError(f"condition_to_sql() 'any' operator accepts Domain, SQL or Query, got {value}")
        sql = SQL(
            "%s%s%s",
            sql_field,
            SQL(" IN ") if positive else SQL(" NOT IN "),
            subselect,
        )
        if can_be_null and not positive:
            sql = SQL("(%s IS NULL OR %s)", sql_field, sql)
        if self.company_dependent:
            sql = self._condition_to_sql_company(sql, field_expr, operator, value, model, alias, query)
        return sql

    def join(self, model: BaseModel, alias: str, query: Query) -> tuple[BaseModel, str]:
        """ Add a LEFT JOIN to ``query`` by following field ``self``,
        and return the joined table's corresponding model and alias.
        """
        comodel = model.env[self.comodel_name]
        coalias = query.make_alias(alias, self.name)
        query.add_join('LEFT JOIN', coalias, comodel._table, SQL(
            "%s = %s",
            model._field_to_sql(alias, self.name, query),
            SQL.identifier(coalias, 'id'),
        ))
        return (comodel, coalias)
