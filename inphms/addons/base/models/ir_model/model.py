from __future__ import annotations
import logging

from inphms.exceptions import ValidationError, UserError
from inphms.tools import _, unique
from .utils import model_xmlid, mark_modified, upsert_en, select_en, MODULE_UNINSTALL_FLAG, \
    RE_ORDER_FIELDS
from inphms.databases import SQL, sqlutils
from inphms.orm.models.utils import MAGIC_COLUMNS, check_object_name
from inphms.orm.fields import Command
from inphms.orm import fields, models, api
from inphms import tools

_logger = logging.getLogger(__name__)


class IrModel(models.Model):
    _name = 'ir.model'
    _description = "Models"
    _order = 'model'
    _rec_names_search = ['name', 'model']
    _allow_sudo_commands = False

    def _default_field_id(self):
        if self.env.context.get('install_mode'):
            return []                   # no default field when importing
        return [Command.create({'name': 'x_name', 'field_description': 'Name', 'ttype': 'char', 'copied': True})]

    name = fields.Char(string='Model Description', translate=True, required=True)
    model = fields.Char(default='x_', required=True)
    order = fields.Char(string='Order', default='id', required=True,
                        help='SQL expression for ordering records in the model; e.g. "x_sequence asc, id desc"')
    info = fields.Text(string='Information')
    field_id = fields.One2many('ir.model.fields', 'model_id', string='Fields', required=True, copy=True,
                               default=_default_field_id)
    inherited_model_ids = fields.Many2many('ir.model', compute='_inherited_models', string="Inherited models",
                                           help="The list of models that extends the current model.")
    state = fields.Selection([('manual', 'Custom Object'), ('base', 'Base Object')], string='Type', default='manual', readonly=True)
    access_ids = fields.One2many('ir.model.access', 'model_id', string='Access')
    rule_ids = fields.One2many('ir.rule', 'model_id', string='Record Rules')
    abstract = fields.Boolean(string="Abstract Model")
    transient = fields.Boolean(string="Transient Model")
    modules = fields.Char(compute='_in_modules', string='In Apps', help='List of modules in which the object is defined or inherited')
    view_ids = fields.One2many('ir.ui.view', compute='_view_ids', string='Views')
    count = fields.Integer(compute='_compute_count', string="Count (Incl. Archived)",
                           help="Total number of records in this model")
    fold_name = fields.Char(string="Fold Field", help="In a Kanban view where columns are records of this model, the value "
        "of this (boolean) field determines which column should be folded by default.")

    @api.depends()
    def _inherited_models(self):
        self.inherited_model_ids = False
        for model in self:
            records = self.env.get(model.model)
            if records is not None:
                model.inherited_model_ids = self.search([('model', 'in', list(records._inherits))])

    @api.depends()
    def _in_modules(self):
        installed_modules = self.env['ir.module.module'].search([('state', '=', 'installed')])
        installed_names = set(installed_modules.mapped('name'))
        xml_ids = models.Model._get_external_ids(self)
        for model in self:
            module_names = set(xml_id.split('.')[0] for xml_id in xml_ids[model.id])
            model.modules = ", ".join(sorted(installed_names & module_names))

    @api.depends()
    def _view_ids(self):
        for model in self:
            model.view_ids = self.env['ir.ui.view'].search([('model', '=', model.model)])

    @api.depends()
    def _compute_count(self):
        self.count = 0
        for model in self:
            records = self.env.get(model.model)
            if records is not None and not records._abstract and records._auto:
                [[count]] = self.env.execute_query(SQL("SELECT COUNT(*) FROM %s", SQL.identifier(records._table)))
                model.count = count

    @api.constrains('model')
    def _check_model_name(self):
        for model in self:
            if model.state == 'manual':
                self._check_manual_name(model.model)
            if not check_object_name(model.model):
                raise ValidationError(_("The model name can only contain lowercase characters, digits, underscores and dots."))

    @api.constrains('order', 'field_id')
    def _check_order(self):
        for model in self:
            try:
                model._check_qorder(model.order)  # regex check for the whole clause ('is it valid sql?')
            except UserError as e:
                raise ValidationError(str(e))
            # add MAGIC_COLUMNS to 'stored_fields' in case 'model' has not been
            # initialized yet, or 'field_id' is not up-to-date in cache
            stored_fields = set(
                model.field_id.filtered('store').mapped('name') + MAGIC_COLUMNS
            )
            if model.model in self.env:
                # add fields inherited from models specified via code if they are already loaded
                stored_fields.update(
                    fname
                    for fname, fval in self.env[model.model]._fields.items()
                    if fval.inherited and fval.base_field.store
                )

            order_fields = RE_ORDER_FIELDS.findall(model.order)
            for field in order_fields:
                if field not in stored_fields:
                    raise ValidationError(_("Unable to order by %s: fields used for ordering must be present on the model and stored.", field))

    @api.constrains('fold_name')
    def _check_fold_name(self):
        for model in self:
            if model.fold_name and model.fold_name not in model.field_id.mapped('name'):
                raise ValidationError(_("The value of 'Fold Field' should be a field name of the model."))

    _obj_name_uniq = models.Constraint('UNIQUE (model)', 'Each model must have a unique name.')

    def _get(self, name):
        """ Return the (sudoed) `ir.model` record with the given name.
        The result may be an empty recordset if the model is not found.
        """
        model_id = self._get_id(name) if name else False
        return self.sudo().browse(model_id)

    @tools.ormcache('name', cache='stable')
    def _get_id(self, name):
        self.env.cr.execute("SELECT id FROM ir_model WHERE model=%s", (name,))
        result = self.env.cr.fetchone()
        return result and result[0]

    def _drop_table(self):
        for model in self:
            current_model = self.env.get(model.model)
            if current_model is not None:
                if current_model._abstract:
                    continue

                table = current_model._table
                kind = sqlutils.table_kind(self.env.cr, table)
                if kind == sqlutils.TableKind.View:
                    self.env.cr.execute(SQL('DROP VIEW %s', SQL.identifier(table)))
                elif kind == sqlutils.TableKind.Regular:
                    self.env.cr.execute(SQL('DROP TABLE %s CASCADE', SQL.identifier(table)))
                elif kind is not None:
                    _logger.warning(
                        "Unable to drop table %r of model %r: unmanaged or unknown tabe type %r",
                        table, model.model, kind
                    )
            else:
                _logger.runbot('The model %s could not be dropped because it did not exist in the registry.', model.model)
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_if_manual(self):
        # Prevent manual deletion of module tables
        for model in self:
            if model.state != 'manual':
                raise UserError(_("Model “%s” contains module data and cannot be removed.", model.name))

    def unlink(self):
        # prevent screwing up fields that depend on these models' fields
        manual_models = self.filtered(lambda model: model.state == 'manual')
        manual_models.field_id.filtered(lambda f: f.state == 'manual')._prepare_update()
        (self - manual_models).field_id._prepare_update()

        # delete fields whose comodel is being removed
        self.env['ir.model.fields'].search([('relation', 'in', self.mapped('model'))]).unlink()

        # delete ir_crons created by user
        crons = self.env['ir.cron'].with_context(active_test=False).search([('model_id', 'in', self.ids)])
        if crons:
            crons.unlink()

        self._drop_table()
        res = super().unlink()

        # Reload registry for normal unlink only. For module uninstall, the
        # reload is done independently in inphms.modules.loading.
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            # setup models; this automatically removes model from registry
            self.env.flush_all()
            self.pool._setup_models__(self.env.cr)

        return res

    def write(self, vals):
        for unmodifiable_field in ('model', 'state', 'abstract', 'transient'):
            if unmodifiable_field in vals and any(rec[unmodifiable_field] != vals[unmodifiable_field] for rec in self):
                raise UserError(_('Field %s cannot be modified on models.', self._fields[unmodifiable_field]._description_string(self.env)))
        # Filter out operations 4 from field id, because the web client always
        # writes (4,id,False) even for non dirty items.
        if 'field_id' in vals:
            vals['field_id'] = [op for op in vals['field_id'] if op[0] != 4]
        res = super().write(vals)
        # ordering has been changed, reload registry to reflect update + signaling
        if 'order' in vals or 'fold_name' in vals:
            self.env.flush_all()  # _setup_models__ need to fetch the updated values from the db
            # incremental setup will reload custom models
            self.pool._setup_models__(self.env.cr, [])
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        manual_models = [
            vals['model'] for vals in vals_list if vals.get('state', 'manual') == 'manual'
        ]
        if manual_models:
            # setup models; this automatically adds model in registry
            self.env.flush_all()
            # incremental setup will reload custom models
            self.pool._setup_models__(self.env.cr, [])
            # update database schema
            self.pool.init_models(self.env.cr, manual_models, dict(self.env.context, update_custom_fields=True))
        return res

    @api.model
    def name_create(self, name):
        """ Infer the model from the name. E.g.: 'My New Model' should become 'x_my_new_model'. """
        ir_model = self.create({
            'name': name,
            'model': 'x_' + '_'.join(name.lower().split(' ')),
        })
        return ir_model.id, ir_model.display_name

    def _reflect_model_params(self, model):
        """ Return the values to write to the database for the given model. """
        return {
            'model': model._name,
            'name': model._description,
            'order': model._order,
            'info': next(cls.__doc__ for cls in self.env.registry[model._name].mro() if cls.__doc__),
            'state': 'manual' if model._custom else 'base',
            'abstract': model._abstract,
            'transient': model._transient,
            'fold_name': model._fold_name,
        }

    def _reflect_models(self, model_names):
        """ Reflect the given models. """
        # determine expected and existing rows
        rows = [
            self._reflect_model_params(self.env[model_name])
            for model_name in model_names
        ]
        cols = list(unique(['model'] + list(rows[0])))
        expected = [tuple(row[col] for col in cols) for row in rows]

        model_ids = {}
        existing = {}
        for row in select_en(self, ['id'] + cols, model_names):
            model_ids[row[1]] = row[0]
            existing[row[1]] = row[1:]

        # create or update rows
        rows = [row for row in expected if existing.get(row[0]) != row]
        if rows:
            ids = upsert_en(self, cols, rows, ['model'])
            for row, id_ in zip(rows, ids):
                model_ids[row[0]] = id_
            self.pool.post_init(mark_modified, self.browse(ids), cols[1:])

        # update their XML id
        module = self.env.context.get('module')
        if not module:
            return

        data_list = []
        for model_name, model_id in model_ids.items():
            model = self.env[model_name]
            if model._module == module:
                # model._module is the name of the module that last extended model
                xml_id = model_xmlid(module, model_name)
                record = self.browse(model_id)
                data_list.append({'xml_id': xml_id, 'record': record})
        self.env['ir.model.data']._update_xmlids(data_list)

    @api.model
    def _instanciate_attrs(self, model_data):
        """ Return the attributes to instanciate a custom model definition class
            corresponding to ``model_data``.
        """
        return {
            '_name': model_data['model'],
            '_description': model_data['name'],
            '_module': False,
            '_custom': True,
            '_abstract': bool(model_data['abstract']),
            '_transient': bool(model_data['transient']),
            '_order': model_data['order'],
            '_fold_name': model_data['fold_name'],
            '__doc__': model_data['info'],
        }

    @api.model
    def _is_manual_name(self, name):
        return name.startswith('x_')

    @api.model
    def _check_manual_name(self, name):
        if not self._is_manual_name(name):
            raise ValidationError(_("The model name must start with 'x_'."))
