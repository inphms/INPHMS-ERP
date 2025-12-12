from __future__ import annotations
import typing as t

from operator import attrgetter
from collections import defaultdict

from inphms.tools import unique, OrderedSet
from ..numeric import Integer


if t.TYPE_CHECKING:
    from ...models import BaseModel

class Many2oneReference(Integer):
    """ Pseudo-relational field (no FK in database).

        The field value is stored as an :class:`integer <int>` id in database.

        Contrary to :class:`Reference` fields, the model has to be specified
        in a :class:`Char` field, whose name has to be specified in the
        `model_field` attribute for the current :class:`Many2oneReference` field.

        :param str model_field: name of the :class:`Char` where the model name is stored.
    """
    type = 'many2one_reference'

    model_field = None
    aggregator = None

    _related_model_field = property(attrgetter('model_field'))

    _description_model_field = property(attrgetter('model_field'))

    def convert_to_cache(self, value, record, validate=True):
        # cache format: id or None
        from ...models import BaseModel
        if isinstance(value, BaseModel):
            value = value._ids[0] if value._ids else None
        return super().convert_to_cache(value, record, validate)

    def _update_inverses(self, records: BaseModel, value):
        """ Add `records` to the cached values of the inverse fields of `self`. """
        if not value:
            return
        model_ids = self._record_ids_per_res_model(records)

        for invf in records.pool.field_inverses[self]:
            records = records.browse(model_ids[invf.model_name])
            if not records:
                continue
            corecord = records.env[invf.model_name].browse(value)
            records = records.filtered_domain(invf.get_comodel_domain(corecord))
            if not records:
                continue
            ids0 = invf._get_cache(corecord.env).get(corecord.id)
            # if the value for the corecord is not in cache, but this is a new
            # record, assign it anyway, as you won't be able to fetch it from
            # database (see `test_sale_order`)
            if ids0 is not None or not corecord.id:
                ids1 = tuple(unique((ids0 or ()) + records._ids))
                invf._update_cache(corecord, ids1)

    def _record_ids_per_res_model(self, records: BaseModel) -> dict[str, OrderedSet]:
        model_ids = defaultdict(OrderedSet)
        for record in records:
            model = record[self.model_field]
            if not model and record._fields[self.model_field].compute:
                # fallback when the model field is computed :-/
                record._fields[self.model_field].compute_value(record)
                model = record[self.model_field]
                if not model:
                    continue
            model_ids[model].add(record.id)
        return model_ids
