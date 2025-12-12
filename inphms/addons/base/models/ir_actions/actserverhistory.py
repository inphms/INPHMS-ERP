from __future__ import annotations
import pytz
import babel

from inphms.tools import get_lang, _, get_diff
from inphms.orm import fields, api, models
from inphms.server.utils import request


class IrActionsServerHistory(models.Model):
    _name = 'ir.actions.server.history'
    _description = 'Server Action History'
    _order = 'create_date desc, id desc'
    _max_entries_per_action = 100

    action_id = fields.Many2one('ir.actions.server', required=True, ondelete='cascade')
    code = fields.Text()

    def _compute_display_name(self):
        self.display_name = False
        for history in self.filtered('create_date'):
            locale = get_lang(self.env).code
            tzinfo = pytz.timezone(self.env.user.tz)
            datetime = history.create_date.replace(microsecond=0)
            datetime = pytz.utc.localize(datetime, is_dst=False)
            datetime = datetime.astimezone(tzinfo) if tzinfo else datetime
            date_label = babel.dates.format_datetime(
                datetime,
                tzinfo=tzinfo,
                locale=locale,
            )
            author = history.create_uid.name
            history.display_name = _("%(date_label)s - %(author)s", date_label=date_label, author=author)

    @api.autovacuum
    def _gc_histories(self):
        result = self._read_group(
            domain=[],
            groupby=["action_id"],
            aggregates=["id:recordset"],
            having=[("__count", ">", self._max_entries_per_action)],
        )
        to_clean = self
        for _action_id, history_ids in result:
            to_clean |= history_ids.sorted()[self._max_entries_per_action:]
        to_clean.unlink()


class ServerActionHistoryWizard(models.TransientModel):
    """ A wizard to compare and reset server action code. """
    _name = 'server.action.history.wizard'
    _description = "Server Action History Wizard"

    @api.model
    def _default_revision(self):
        action_id = self.env['ir.actions.server'].browse(self.env.context.get('default_action_id', False))
        return self.env["ir.actions.server.history"].search([
            ("action_id", "=", action_id.id),
            ('code', '!=', action_id.code),
        ], limit=1)

    action_id = fields.Many2one('ir.actions.server')
    code_diff = fields.Html(compute='_compute_code_diff', sanitize_tags=False)
    current_code = fields.Text(related='action_id.code', readonly=True)
    revision = fields.Many2one("ir.actions.server.history",
        domain="[('action_id', '=', action_id), ('code', '!=', current_code)]",
        default=_default_revision,
        required=True,
    )

    @api.depends("revision")
    def _compute_code_diff(self):
        for wizard in self:
            rev_code = wizard.revision.code
            actual_code = wizard.action_id.code
            has_diff = actual_code != rev_code
            wizard.code_diff = get_diff(
                    (actual_code or "", _("Actual Code")),
                    (rev_code or "", _("Revision Code")),
                    dark_color_scheme=request and request.cookies.get("color_scheme") == "dark",
            ) if has_diff else False

    def restore_revision(self):
        self.ensure_one()
        self.action_id.code = self.revision.code
