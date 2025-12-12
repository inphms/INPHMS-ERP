from __future__ import annotations

from inphms.tools._vendor.safe_eval import safe_eval
from inphms.orm import fields, api, models


class IrActionsClient(models.Model):
    _name = 'ir.actions.client'
    _description = 'Client Action'
    _inherit = ['ir.actions.actions']
    _table = 'ir_act_client'
    _order = 'name, id'
    _allow_sudo_commands = False

    type = fields.Char(default='ir.actions.client')

    tag = fields.Char(string='Client action tag', required=True,
                      help="An arbitrary string, interpreted by the client"
                           " according to its own needs and wishes. There "
                           "is no central tag repository across clients.")
    target = fields.Selection([('current', 'Current Window'), ('new', 'New Window'), ('fullscreen', 'Full Screen'), ('main', 'Main action of Current Window')], default="current", string='Target Window')
    res_model = fields.Char(string='Destination Model', help="Optional model, mostly used for needactions.")
    context = fields.Char(string='Context Value', default="{}", required=True, help="Context dictionary as Python expression, empty by default (Default: {})")
    params = fields.Binary(compute='_compute_params', inverse='_inverse_params', string='Supplementary arguments',
                           help="Arguments sent to the client along with "
                                "the view tag")
    params_store = fields.Binary(string='Params storage', readonly=True, attachment=False)

    @api.depends('params_store')
    def _compute_params(self):
        self_bin = self.with_context(bin_size=False, bin_size_params_store=False)
        for record, record_bin in zip(self, self_bin):
            record.params = record_bin.params_store and safe_eval(record_bin.params_store, {'uid': self.env.uid})

    def _inverse_params(self):
        for record in self:
            params = record.params
            record.params_store = repr(params) if isinstance(params, dict) else params


    def _get_readable_fields(self):
        return super()._get_readable_fields() | {
            "context", "params", "res_model", "tag", "target",
        }
