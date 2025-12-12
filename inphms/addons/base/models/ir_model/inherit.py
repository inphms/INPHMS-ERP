from __future__ import annotations

from collections import defaultdict

from .utils import mark_modified, upsert_en
from inphms.orm.model_classes import is_model_definition
from inphms.tools import OrderedSet
from inphms.orm import models, fields


class IrModelInherit(models.Model):
    _name = 'ir.model.inherit'
    _description = "Model Inheritance Tree"
    _log_access = False

    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    parent_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    parent_field_id = fields.Many2one("ir.model.fields", ondelete="cascade")  # in case of inherits

    _uniq = models.Constraint("UNIQUE(model_id, parent_id)", "Models inherits from another only once")

    def _reflect_inherits(self, model_names):
        """ Reflect the given models' inherits (_inherit and _inherits). """
        IrModel = self.env["ir.model"]
        get_model_id = IrModel._get_id

        module_mapping = defaultdict(OrderedSet)
        for model_name in model_names:
            get_field_id = self.env["ir.model.fields"]._get_ids(model_name).get
            model_id = get_model_id(model_name)
            model = self.env[model_name]

            for cls in reversed(type(model).mro()):
                if not is_model_definition(cls):
                    continue

                items = [
                    (model_id, get_model_id(parent_name), None)
                    for parent_name in cls._inherit
                    if parent_name not in ("base", model_name)
                ] + [
                    (model_id, get_model_id(parent_name), get_field_id(field))
                    for parent_name, field in cls._inherits.items()
                ]

                for item in items:
                    module_mapping[item].add(cls._module)

        if not module_mapping:
            return

        cr = self.env.cr
        cr.execute(
            """
                SELECT i.id, i.model_id, i.parent_id, i.parent_field_id
                  FROM ir_model_inherit i
                  JOIN ir_model m
                    ON m.id = i.model_id
                 WHERE m.model IN %s
            """,
            [tuple(model_names)]
        )
        existing = {}
        inh_ids = {}
        for iid, model_id, parent_id, parent_field_id in cr.fetchall():
            inh_ids[(model_id, parent_id, parent_field_id)] = iid
            existing[(model_id, parent_id)] = parent_field_id

        sentinel = object()
        cols = ["model_id", "parent_id", "parent_field_id"]
        rows = [item for item in module_mapping if existing.get(item[:2], sentinel) != item[2]]
        if rows:
            ids = upsert_en(self, cols, rows, ["model_id", "parent_id"])
            for row, id_ in zip(rows, ids):
                inh_ids[row] = id_
            self.pool.post_init(mark_modified, self.browse(ids), cols[1:])

        # update their XML id
        IrModel.browse(id_ for item in module_mapping for id_ in item[:2]).fetch(['model'])
        data_list = []
        for (model_id, parent_id, parent_field_id), modules in module_mapping.items():
            model_name = IrModel.browse(model_id).model.replace(".", "_")
            parent_name = IrModel.browse(parent_id).model.replace(".", "_")
            record_id = inh_ids[(model_id, parent_id, parent_field_id)]
            data_list += [
                {
                    "xml_id": f"{module}.model_inherit__{model_name}__{parent_name}",
                    "record": self.browse(record_id),
                }
                for module in modules
            ]

        self.env["ir.model.data"]._update_xmlids(data_list)
