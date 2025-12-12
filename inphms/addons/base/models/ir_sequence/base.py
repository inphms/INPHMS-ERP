from __future__ import annotations
import logging

from datetime import datetime, timedelta

from .utils import _predict_nextval, _create_sequence, _drop_sequences, _alter_sequence, _select_nextval, _update_nogap, UserError, _
from inphms.orm import models, api, fields

_logger = logging.getLogger(__name__)


class IrSequence(models.Model):
    """ Sequence model.

    The sequence model allows to define and use so-called sequence objects.
    Such objects are used to generate unique identifiers in a transaction-safe
    way.

    """
    _name = 'ir.sequence'
    _description = 'Sequence'
    _order = 'name, id'
    _allow_sudo_commands = False

    def _get_number_next_actual(self):
        '''Return number from ir_sequence row when no_gap implementation,
        and number from postgres sequence when standard implementation.'''
        for seq in self:
            if not seq.id:
                seq.number_next_actual = 0
            elif seq.implementation != 'standard':
                seq.number_next_actual = seq.number_next
            else:
                seq_id = "%03d" % seq.id
                seq.number_next_actual = _predict_nextval(self, seq_id)

    def _set_number_next_actual(self):
        for seq in self:
            seq.write({'number_next': seq.number_next_actual or 1})

    @api.model
    def _get_current_sequence(self, sequence_date=None):
        '''Returns the object on which we can find the number_next to consider for the sequence.
        It could be an ir.sequence or an ir.sequence.date_range depending if use_date_range is checked
        or not. This function will also create the ir.sequence.date_range if none exists yet for today
        '''
        if not self.use_date_range:
            return self
        sequence_date = sequence_date or fields.Date.today()
        seq_date = self.env['ir.sequence.date_range'].search(
            [('sequence_id', '=', self.id), ('date_from', '<=', sequence_date), ('date_to', '>=', sequence_date)], limit=1)
        if seq_date:
            return seq_date[0]
        #no date_range sequence was found, we create a new one
        return self._create_date_range_seq(sequence_date)

    name = fields.Char(required=True)
    code = fields.Char(string='Sequence Code')
    implementation = fields.Selection([('standard', 'Standard'), ('no_gap', 'No gap')],
                                      string='Implementation', required=True, default='standard',
                                      help="While assigning a sequence number to a record, the 'no gap' sequence implementation ensures that each previous sequence number has been assigned already. "
                                      "While this sequence implementation will not skip any sequence number upon assignment, there can still be gaps in the sequence if records are deleted. "
                                      "The 'no gap' implementation is slower than the standard one.")
    active = fields.Boolean(default=True)
    prefix = fields.Char(help="Prefix value of the record for the sequence", trim=False)
    suffix = fields.Char(help="Suffix value of the record for the sequence", trim=False)
    number_next = fields.Integer(string='Next Number', required=True, default=1, help="Next number of this sequence")
    number_next_actual = fields.Integer(compute='_get_number_next_actual', inverse='_set_number_next_actual',
                                        string='Actual Next Number',
                                        help="Next number that will be used. This number can be incremented "
                                        "frequently so the displayed value might already be obsolete")
    number_increment = fields.Integer(string='Step', required=True, default=1,
                                      help="The next number of the sequence will be incremented by this number")
    padding = fields.Integer(string='Sequence Size', required=True, default=0,
                             help="Inphms will automatically adds some '0' on the left of the "
                                  "'Next Number' to get the required padding size.")
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda s: s.env.company)
    use_date_range = fields.Boolean(string='Use subsequences per date_range')
    date_range_ids = fields.One2many('ir.sequence.date_range', 'sequence_id', string='Subsequences')

    @api.model_create_multi
    def create(self, vals_list):
        """ Create a sequence, in implementation == standard a fast gaps-allowed PostgreSQL sequence is used.
        """
        seqs = super().create(vals_list)
        for seq in seqs:
            if seq.implementation == 'standard':
                _create_sequence(self.env.cr, "ir_sequence_%03d" % seq.id, seq.number_increment or 1, seq.number_next or 1)
        return seqs

    def unlink(self):
        _drop_sequences(self.env.cr, ["ir_sequence_%03d" % x.id for x in self])
        return super(IrSequence, self).unlink()

    def write(self, vals):
        new_implementation = vals.get('implementation')
        for seq in self:
            # 4 cases: we test the previous impl. against the new one.
            i = vals.get('number_increment', seq.number_increment)
            n = vals.get('number_next', seq.number_next)
            if seq.implementation == 'standard':
                if new_implementation in ('standard', None):
                    # Implementation has NOT changed.
                    # Only change sequence if really requested.
                    if vals.get('number_next'):
                        _alter_sequence(self.env.cr, "ir_sequence_%03d" % seq.id, number_next=n)
                    if seq.number_increment != i:
                        _alter_sequence(self.env.cr, "ir_sequence_%03d" % seq.id, number_increment=i)
                        seq.date_range_ids._alter_sequence(number_increment=i)
                else:
                    _drop_sequences(self.env.cr, ["ir_sequence_%03d" % seq.id])
                    for sub_seq in seq.date_range_ids:
                        _drop_sequences(self.env.cr, ["ir_sequence_%03d_%03d" % (seq.id, sub_seq.id)])
            else:
                if new_implementation in ('no_gap', None):
                    pass
                else:
                    _create_sequence(self.env.cr, "ir_sequence_%03d" % seq.id, i, n)
                    for sub_seq in seq.date_range_ids:
                        _create_sequence(self.env.cr, "ir_sequence_%03d_%03d" % (seq.id, sub_seq.id), i, n)
        res = super().write(vals)
        # DLE P179
        self.flush_model(vals.keys())
        return res

    def _next_do(self):
        if self.implementation == 'standard':
            number_next = _select_nextval(self.env.cr, 'ir_sequence_%03d' % self.id)
        else:
            number_next = _update_nogap(self, self.number_increment)
        return self.get_next_char(number_next)

    def _get_prefix_suffix(self, date=None, date_range=None):
        def _interpolate(s, d):
            return (s % d) if s else ''

        def _interpolation_dict():
            now = range_date = effective_date = datetime.now(self.env.tz)
            if date or self.env.context.get('ir_sequence_date'):
                effective_date = fields.Datetime.from_string(date or self.env.context.get('ir_sequence_date'))
            if date_range or self.env.context.get('ir_sequence_date_range'):
                range_date = fields.Datetime.from_string(date_range or self.env.context.get('ir_sequence_date_range'))

            sequences = {
                'year': '%Y', 'month': '%m', 'day': '%d', 'y': '%y', 'doy': '%j', 'woy': '%W',
                'weekday': '%w', 'h24': '%H', 'h12': '%I', 'min': '%M', 'sec': '%S',
                'isoyear': '%G', 'isoy': '%g', 'isoweek': '%V',
            }
            res = {}
            for key, format in sequences.items():
                res[key] = effective_date.strftime(format)
                res['range_' + key] = range_date.strftime(format)
                res['current_' + key] = now.strftime(format)

            return res

        self.ensure_one()
        d = _interpolation_dict()
        try:
            interpolated_prefix = _interpolate(self.prefix, d)
            interpolated_suffix = _interpolate(self.suffix, d)
        except (ValueError, TypeError, KeyError):
            raise UserError(_('Invalid prefix or suffix for sequence “%s”', self.name))
        return interpolated_prefix, interpolated_suffix

    def get_next_char(self, number_next):
        interpolated_prefix, interpolated_suffix = self._get_prefix_suffix()
        return interpolated_prefix + '%%0%sd' % self.padding % number_next + interpolated_suffix

    def _create_date_range_seq(self, date):
        year = fields.Date.from_string(date).strftime('%Y')
        date_from = '{}-01-01'.format(year)
        date_to = '{}-12-31'.format(year)
        date_range = self.env['ir.sequence.date_range'].search([('sequence_id', '=', self.id), ('date_from', '>=', date), ('date_from', '<=', date_to)], order='date_from desc', limit=1)
        if date_range:
            date_to = date_range.date_from + timedelta(days=-1)
        date_range = self.env['ir.sequence.date_range'].search([('sequence_id', '=', self.id), ('date_to', '>=', date_from), ('date_to', '<=', date)], order='date_to desc', limit=1)
        if date_range:
            date_from = date_range.date_to + timedelta(days=1)
        seq_date_range = self.env['ir.sequence.date_range'].sudo().create({
            'date_from': date_from,
            'date_to': date_to,
            'sequence_id': self.id,
        })
        return seq_date_range

    def _next(self, sequence_date=None):
        """ Returns the next number in the preferred sequence in all the ones given in self."""
        if not self.use_date_range:
            return self._next_do()
        # date mode
        dt = sequence_date or self.env.context.get('ir_sequence_date', fields.Date.today())
        seq_date = self.env['ir.sequence.date_range'].search([('sequence_id', '=', self.id), ('date_from', '<=', dt), ('date_to', '>=', dt)], limit=1)
        if not seq_date:
            seq_date = self._create_date_range_seq(dt)
        return seq_date.with_context(ir_sequence_date_range=seq_date.date_from)._next()

    def next_by_id(self, sequence_date=None):
        """ Draw an interpolated string using the specified sequence."""
        self.browse().check_access('read')
        return self._next(sequence_date=sequence_date)

    @api.model
    def next_by_code(self, sequence_code, sequence_date=None):
        """ Draw an interpolated string using a sequence with the requested code.
            If several sequences with the correct code are available to the user
            (multi-company cases), the one from the user's current company will
            be used.
        """
        self.browse().check_access('read')
        company_id = self.env.company.id
        seq_ids = self.search([('code', '=', sequence_code), ('company_id', 'in', [company_id, False])], order='company_id')
        if not seq_ids:
            _logger.debug("No ir.sequence has been found for code '%s'. Please make sure a sequence is set for current company." % sequence_code)
            return False
        seq_id = seq_ids[0]
        return seq_id._next(sequence_date=sequence_date)
