from __future__ import annotations
import datetime
import os
import binascii

from hashlib import sha256

from .user import _logger
from .utils import check_identity, CryptContext, request
from inphms.databases import SQL
from inphms.tools import _
from inphms.exceptions import AccessError, ValidationError, UserError
from inphms.orm import models, fields, api


#########
# CONST #
#########
# API keys support
API_KEY_SIZE = 20 # in bytes
INDEX_SIZE = 8 # in hex digits, so 4 bytes, or 20% of the key
KEY_CRYPT_CONTEXT = CryptContext(
    # default is 29000 rounds which is 25~50ms, which is probably unnecessary
    # given in this case all the keys are completely random data: dictionary
    # attacks on API keys isn't much of a concern
    ['pbkdf2_sha512'], pbkdf2_sha512__rounds=6000,
)

#########
# CLASS #
#########
class ResUsersApikeys(models.Model):
    _name = 'res.users.apikeys'
    _description = 'Users API Keys'
    _auto = False # so we can have a secret column
    _allow_sudo_commands = False

    name = fields.Char("Description", required=True, readonly=True)
    user_id = fields.Many2one('res.users', index=True, required=True, readonly=True, ondelete="cascade")
    scope = fields.Char("Scope", readonly=True)
    create_date = fields.Datetime("Creation Date", readonly=True)
    expiration_date = fields.Datetime("Expiration Date", readonly=True)

    def init(self):
        table = SQL.identifier(self._table)
        self.env.cr.execute(SQL("""
        CREATE TABLE IF NOT EXISTS %(table)s (
            id serial primary key,
            name varchar not null,
            user_id integer not null REFERENCES res_users(id) ON DELETE CASCADE,
            scope varchar,
            expiration_date timestamp without time zone,
            index varchar(%(index_size)s) not null CHECK (char_length(index) = %(index_size)s),
            key varchar not null,
            create_date timestamp without time zone DEFAULT (now() at time zone 'utc')
        )
        """, table=table, index_size=INDEX_SIZE))

        index_name = self._table + "_user_id_index_idx"
        if len(index_name) > 63:
            # unique determinist index name
            index_name = self._table[:50] + "_idx_" + sha256(self._table.encode()).hexdigest()[:8]
        self.env.cr.execute(SQL(
            "CREATE INDEX IF NOT EXISTS %s ON %s (user_id, index)",
            SQL.identifier(index_name),
            table,
        ))

    @check_identity
    def remove(self):
        return self._remove()

    def _remove(self):
        """Use the remove() method to remove an API Key. This method implement logic,
        but won't check the identity (mainly used to remove trusted devices)"""
        if not self:
            return {'type': 'ir.actions.act_window_close'}
        if self.env.is_system() or self.mapped('user_id') == self.env.user:
            ip = request.httprequest.environ['REMOTE_ADDR'] if request else 'n/a'
            _logger.info("API key(s) removed: scope: <%s> for '%s' (#%s) from %s",
               self.mapped('scope'), self.env.user.login, self.env.uid, ip)
            self.sudo().unlink()
            return {'type': 'ir.actions.act_window_close'}
        raise AccessError(_("You can not remove API keys unless they're yours or you are a system user"))

    def _check_credentials(self, *, scope, key):
        assert scope and key, "scope and key required"
        index = key[:INDEX_SIZE]
        self.env.cr.execute('''
            SELECT user_id, key
            FROM {} INNER JOIN res_users u ON (u.id = user_id)
            WHERE
                u.active and index = %s
                AND (scope IS NULL OR scope = %s)
                AND (
                    expiration_date IS NULL OR
                    expiration_date >= now() at time zone 'utc'
                )
        '''.format(self._table),
        [index, scope])
        for user_id, current_key in self.env.cr.fetchall():
            if key and KEY_CRYPT_CONTEXT.verify(key, current_key):
                return user_id

    def _check_expiration_date(self, date):
        # To be in a sudoed environment or to be an administrator
        # to create a persistent key (no expiration date) or
        # to exceed the maximum duration determined by the user's privileges.
        if self.env.is_system():
            return
        if not date:
            raise ValidationError(_("The API key must have an expiration date"))
        max_duration = max(group.api_key_duration for group in self.env.user.all_group_ids) or 1.0
        if date > datetime.datetime.now() + datetime.timedelta(days=max_duration):
            raise ValidationError(_("You cannot exceed %(duration)s days.", duration=max_duration))

    def _generate(self, scope, name, expiration_date):
        """Generates an api key.
        :param str scope: the scope of the key. If None, the key will give access to any rpc.
        :param str name: the name of the key, mainly intended to be displayed in the UI.
        :param date expiration_date: the expiration date of the key.
        :return: str: the key.

        Note:
        This method must be called in sudo to use a duration
        greater than that allowed by the user's privileges.
        For a persistent key (infinite duration), no value for expiration date.
        """
        self._check_expiration_date(expiration_date)
        # no need to clear the LRU when *adding* a key, only when removing
        k = binascii.hexlify(os.urandom(API_KEY_SIZE)).decode()
        self.env.cr.execute("""
        INSERT INTO {table} (name, user_id, scope, expiration_date, key, index)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """.format(table=self._table),
        [name, self.env.user.id, scope, expiration_date or None, KEY_CRYPT_CONTEXT.hash(k), k[:INDEX_SIZE]])

        ip = request.httprequest.environ['REMOTE_ADDR'] if request else 'n/a'
        _logger.info("%s generated: scope: <%s> for '%s' (#%s) from %s",
            self._description, scope, self.env.user.login, self.env.uid, ip)

        return k

    @api.autovacuum
    def _gc_user_apikeys(self):
        self.env.cr.execute(SQL("""
            DELETE FROM %s
            WHERE
                expiration_date IS NOT NULL AND
                expiration_date < now() at time zone 'utc'
        """, SQL.identifier(self._table)))
        _logger.info("GC %r delete %d entries", self._name, self.env.cr.rowcount)


class ResUsersApikeysDescription(models.TransientModel):
    _name = 'res.users.apikeys.description'
    _description = 'API Key Description'

    def _selection_duration(self):
        # duration value is a string representing the number of days.
        durations = [
            ('1', '1 Day'),
            ('7', '1 Week'),
            ('30', '1 Month'),
            ('90', '3 Months'),
            ('180', '6 Months'),
            ('365', '1 Year'),
        ]
        persistent_duration = ('0', 'Persistent Key')  # Magic value to detect an infinite duration
        custom_duration = ('-1', 'Custom Date')  # Will force the user to enter a date manually
        if self.env.is_system():
            return durations + [persistent_duration, custom_duration]
        max_duration = max(group.api_key_duration for group in self.env.user.all_group_ids) or 1.0
        return list(filter(
            lambda duration: int(duration[0]) <= max_duration, durations
        )) + [custom_duration]

    name = fields.Char("Description", required=True)
    duration = fields.Selection(
        selection='_selection_duration', string='Duration', required=True,
        default=lambda self: self._selection_duration()[0][0]
    )
    expiration_date = fields.Datetime('Expiration Date', compute='_compute_expiration_date', store=True, readonly=False)

    @api.depends('duration')
    def _compute_expiration_date(self):
        for record in self:
            duration = int(record.duration)
            if duration >= 0:
                record.expiration_date = (
                    fields.Date.today() + datetime.timedelta(days=duration)
                    if int(record.duration)
                    else None
                )

    @api.onchange('expiration_date')
    def _onchange_expiration_date(self):
        try:
            self.env['res.users.apikeys']._check_expiration_date(self.expiration_date)
        except UserError as error:
            warning = {
                'type': 'notification',
                'title': _('The API key duration is not correct.'),
                'message': error.args[0]
            }
            return {'warning': warning}

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self.env['res.users.apikeys']._check_expiration_date(res.expiration_date)
        return res

    @check_identity
    def make_key(self):
        # only create keys for users who can delete their keys
        self.check_access_make_key()

        description = self.sudo()
        k = self.env['res.users.apikeys']._generate(None, description.name, self.expiration_date)
        description.unlink()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.users.apikeys.show',
            'name': _('API Key Ready'),
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_key': k,
            }
        }

    def check_access_make_key(self):
        if not self.env.user._is_internal():
            raise AccessError(_("Only internal users can create API keys"))


class ResUsersApikeysShow(models.AbstractModel):
    _name = 'res.users.apikeys.show'
    _description = 'Show API Key'

    # the field 'id' is necessary for the onchange that returns the value of 'key'
    id = fields.Id()
    key = fields.Char(readonly=True)
