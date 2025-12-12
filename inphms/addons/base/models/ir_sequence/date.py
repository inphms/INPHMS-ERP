from __future__ import annotations

from .utils import _predict_nextval, _alter_sequence, _update_nogap, _select_nextval, _create_sequence, _drop_sequences
from inphms.orm import models, api, fields


class IrSequenceDate_Range(models.Model):
    _name = 'ir.sequence.date_range'
    _description = 'Sequence Date Range'
    _rec_name = "sequence_id"
    _allow_sudo_commands = False

    _unique_range_per_sequence = models.Constraint(
        'UNIQUE(sequence_id, date_from, date_to)',
        "You cannot create two date ranges for the same sequence with the same date range.",
    )

    def _get_number_next_actual(self):
        '''Return number from ir_sequence row when no_gap implementation,
        and number from postgres sequence when standard implementation.'''
        for seq in self:
            if seq.sequence_id.implementation != 'standard':
                seq.number_next_actual = seq.number_next
            else:
                seq_id = "%03d_%03d" % (seq.sequence_id.id, seq.id)
                seq.number_next_actual = _predict_nextval(self, seq_id)

    def _set_number_next_actual(self):
        for seq in self:
            seq.write({'number_next': seq.number_next_actual or 1})

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if 'number_next_actual' in fields:
            result['number_next_actual'] = 1
        return result

    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    sequence_id = fields.Many2one("ir.sequence", string='Main Sequence', required=True, ondelete='cascade')
    number_next = fields.Integer(string='Next Number', required=True, default=1, help="Next number of this sequence")
    number_next_actual = fields.Integer(compute='_get_number_next_actual', inverse='_set_number_next_actual',
                                        string='Actual Next Number',
                                        help="Next number that will be used. This number can be incremented "
                                             "frequently so the displayed value might already be obsolete")

    def _next(self):
        if self.sequence_id.implementation == 'standard':
            number_next = _select_nextval(self.env.cr, 'ir_sequence_%03d_%03d' % (self.sequence_id.id, self.id))
        else:
            number_next = _update_nogap(self, self.sequence_id.number_increment)
        return self.sequence_id.get_next_char(number_next)

    def _alter_sequence(self, number_increment=None, number_next=None):
        for seq in self:
            _alter_sequence(self.env.cr, "ir_sequence_%03d_%03d" % (seq.sequence_id.id, seq.id), number_increment=number_increment, number_next=number_next)

    @api.model_create_multi
    def create(self, vals_list):
        """ Create a sequence, in implementation == standard a fast gaps-allowed PostgreSQL sequence is used.
        """
        seqs = super().create(vals_list)
        for seq in seqs:
            main_seq = seq.sequence_id
            if main_seq.implementation == 'standard':
                _create_sequence(self.env.cr, "ir_sequence_%03d_%03d" % (main_seq.id, seq.id), main_seq.number_increment, seq.number_next_actual or 1)
        return seqs

    def unlink(self):
        _drop_sequences(self.env.cr, ["ir_sequence_%03d_%03d" % (x.sequence_id.id, x.id) for x in self])
        return super().unlink()

    def write(self, vals):
        if vals.get('number_next'):
            seq_to_alter = self.filtered(lambda seq: seq.sequence_id.implementation == 'standard')
            seq_to_alter._alter_sequence(number_next=vals.get('number_next'))
        # DLE P179: `test_in_invoice_line_onchange_sequence_number_1`
        # _update_nogap do a select to get the next sequence number_next
        # When changing (writing) the number next of a sequence, the number next must be flushed before doing the select.
        # Normally in such a case, we flush just above the execute, but for the sake of performance
        # I believe this is better to flush directly in the write:
        #  - Changing the number next of a sequence is really really rare,
        #  - But selecting the number next happens a lot,
        # Therefore, if I chose to put the flush just above the select, it would check the flush most of the time for no reason.
        res = super().write(vals)
        self.flush_model(vals.keys())
        return res
