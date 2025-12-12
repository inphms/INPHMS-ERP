from __future__ import annotations

from inphms.databases import SQL
from inphms.exceptions import UserError
from inphms.tools import _


def _create_sequence(cr, seq_name, number_increment, number_next):
    """ Create a PostreSQL sequence. """
    if number_increment == 0:
        raise UserError(_('Step must not be zero.'))
    sql = "CREATE SEQUENCE %s INCREMENT BY %%s START WITH %%s" % seq_name
    cr.execute(sql, (number_increment, number_next))


def _drop_sequences(cr, seq_names):
    """ Drop the PostreSQL sequences if they exist. """
    if not seq_names:
        return
    names = SQL(',').join(map(SQL.identifier, seq_names))
    # RESTRICT is the default; it prevents dropping the sequence if an
    # object depends on it.
    cr.execute(SQL("DROP SEQUENCE IF EXISTS %s RESTRICT", names))


def _alter_sequence(cr, seq_name, number_increment=None, number_next=None):
    """ Alter a PostreSQL sequence. """
    if number_increment == 0:
        raise UserError(_("Step must not be zero."))
    cr.execute("SELECT relname FROM pg_class WHERE relkind=%s AND relname=%s", ('S', seq_name))
    if not cr.fetchone():
        # sequence is not created yet, we're inside create() so ignore it, will be set later
        return
    statement = SQL(
        "ALTER SEQUENCE %s%s%s",
        SQL.identifier(seq_name),
        SQL(" INCREMENT BY %s", number_increment) if number_increment is not None else SQL(),
        SQL(" RESTART WITH %s", number_next) if number_next is not None else SQL(),
    )
    cr.execute(statement)


def _select_nextval(cr, seq_name):
    cr.execute("SELECT nextval(%s)", [seq_name])
    return cr.fetchone()


def _update_nogap(self, number_increment):
    self.flush_recordset(['number_next'])
    number_next = self.number_next
    self.env.cr.execute("SELECT number_next FROM %s WHERE id=%%s FOR UPDATE NOWAIT" % self._table, [self.id])
    self.env.cr.execute("UPDATE %s SET number_next=number_next+%%s WHERE id=%%s " % self._table, (number_increment, self.id))
    self.invalidate_recordset(['number_next'])
    return number_next

def _predict_nextval(self, seq_id):
    """Predict next value for PostgreSQL sequence without consuming it"""
    # Cannot use currval() as it requires prior call to nextval()
    seqname = 'ir_sequence_%s' % seq_id
    seqtable = SQL.identifier(seqname)
    query = SQL("""
        SELECT last_value,
            (SELECT increment_by FROM pg_sequences WHERE sequencename = %s),
            is_called
        FROM %s""", seqname, seqtable)
    if self.env.cr._cnx.server_version < 100000:
        query = SQL("SELECT last_value, increment_by, is_called FROM %s", seqtable)
    [(last_value, increment_by, is_called)] = self.env.execute_query(query)
    if is_called:
        return last_value + increment_by
    # sequence has just been RESTARTed to return last_value next time
    return last_value
