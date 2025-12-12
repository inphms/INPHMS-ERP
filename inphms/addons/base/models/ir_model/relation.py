from __future__ import annotations

from .model import _logger
from inphms.databases import SQL, sqlutils
from inphms.tools import OrderedSet, _
from inphms.exceptions import AccessError
from inphms.orm import fields, models

class IrModelRelation(models.Model):
    """
    This model tracks PostgreSQL tables used to implement Inphms many2many
    relations.
    """
    _name = 'ir.model.relation'
    _description = 'Relation Model'
    _allow_sudo_commands = False

    name = fields.Char(string='Relation Name', required=True, index=True,
                       help="PostgreSQL table name implementing a many2many relation.")
    model = fields.Many2one('ir.model', required=True, index=True, ondelete='cascade')
    module = fields.Many2one('ir.module.module', required=True, index=True, ondelete='cascade')
    write_date = fields.Datetime()
    create_date = fields.Datetime()

    def _module_data_uninstall(self):
        """
        Delete PostgreSQL many2many relations tracked by this model.
        """
        if not self.env.is_system():
            raise AccessError(_('Administrator access is required to uninstall a module'))

        ids_set = set(self.ids)
        to_drop = OrderedSet()
        for data in self.sorted(key='id', reverse=True):
            name = data.name

            # double-check we are really going to delete all the owners of this schema element
            self.env.cr.execute("""SELECT id from ir_model_relation where name = %s""", [name])
            external_ids = {x[0] for x in self.env.cr.fetchall()}
            if not external_ids.issubset(ids_set):
                # as installed modules have defined this element we must not delete it!
                continue

            if sqlutils.table_exists(self.env.cr, name):
                to_drop.add(name)

        self.unlink()

        # drop m2m relation tables
        for table in to_drop:
            self.env.cr.execute(SQL('DROP TABLE %s CASCADE', SQL.identifier(table)))
            _logger.info('Dropped table %s', table)

    def _reflect_relation(self, model, table, module):
        """ Reflect the table of a many2many field for the given model, to make
            it possible to delete it later when the module is uninstalled.
        """
        self.env.invalidate_all()
        cr = self.env.cr
        query = """ SELECT 1 FROM ir_model_relation r, ir_module_module m
                    WHERE r.module=m.id AND r.name=%s AND m.name=%s """
        cr.execute(query, (table, module))
        if not cr.rowcount:
            query = """ INSERT INTO ir_model_relation
                            (name, create_date, write_date, create_uid, write_uid, module, model)
                        VALUES (%s,
                                now() AT TIME ZONE 'UTC',
                                now() AT TIME ZONE 'UTC',
                                %s, %s,
                                (SELECT id FROM ir_module_module WHERE name=%s),
                                (SELECT id FROM ir_model WHERE model=%s)) """
            cr.execute(query, (table, self.env.uid, self.env.uid, module, model._name))
