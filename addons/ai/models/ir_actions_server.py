from __future__ import annotations
import json

from inphms.orm import models, fields, api


class IrActionsServer(models.Model):
    """ Add related ai options """
    _name = 'ir.actions.server'
    _inherit = ['ir.actions.server']

    @api.depends('ai_tool_schema')
    def _compute_ai_tool_has_schema(self):
        """
        Checks if the ai_tool_schema field contains valid JSON.
        """
        for record in self:
            if not record.ai_tool_schema:
                record.ai_tool_has_schema = False
                continue
            try:
                # Try to parse the JSON to check if it's valid
                json.loads(record.ai_tool_schema)
                record.ai_tool_has_schema = True
            except json.JSONDecodeError:
                record.ai_tool_has_schema = False

    @api.depends('use_in_ai')
    def _compute_ai_tool_is_candidate(self):
        """
        An action is a candidate to be an AI tool if it's explicitly
        marked with 'use_in_ai'.
        """
        for record in self:
            record.ai_tool_is_candidate = record.use_in_ai
    
    @api.depends('use_in_ai', 'ai_tool_description', 'ai_tool_has_schema')
    def _compute_ai_tool_show_warning(self):
        """
        Show a warning if the action is marked for AI use but is
        missing essential components (description or a valid schema).
        """
        for record in self:
            if record.use_in_ai and (not record.ai_tool_description or not record.ai_tool_has_schema):
                record.ai_tool_show_warning = True
            else:
                record.ai_tool_show_warning = False
    

    ai_action_prompt = fields.Html("AI Action Prompt", store=True, default=False, help='Prompt used by "AI" action')
    ai_tool_allow_end_message = fields.Boolean("Allow End Message",
                                               store=True,
                                               default=False,
                                               help="This tool is automatically provided with `__end_message` param which when provided, the LLM processing loop is terminated.")
    ai_tool_description = fields.Text("AI Tool Description", store=True)
    ai_tool_has_schema = fields.Boolean("Ai Tool Has Schema", compute="_compute_ai_tool_has_schema", store=False)
    ai_tool_ids = fields.Many2many("ir.actions.server",
                                   relation="ai_tool_ids_rel",
                                   column1="parent_id",
                                   column2="tool_id",
                                   string="Tools",
                                   store=True, )
    ai_tool_is_candidate = fields.Boolean("Ai Tool Is Candidate", compute="_compute_ai_tool_is_candidate", store=False)
    ai_tool_schema = fields.Text("AI Schema", store=True, help="JSON containing the values that can be returned by the LLM along with their properties (type, length, ...)")
    ai_tool_show_warning = fields.Boolean("Ai Tool Show Warning", compute="_compute_ai_tool_show_warning", store=False)

    state = fields.Selection(
        tracking=True,
        selection_add=[
            ('ai', 'AI'),
        ],
        ondelete={'ai': 'cascade',}
    )

    use_in_ai = fields.Boolean("Use in AI", store=True, default=False)
