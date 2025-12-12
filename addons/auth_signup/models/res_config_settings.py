from __future__ import annotations

from inphms.orm import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    auth_signup_reset_password = fields.Boolean(
        string='Enable password reset from Login page',
        config_parameter='auth_signup.reset_password')
    auth_signup_uninvited = fields.Selection(
        selection=[
            ('b2b', 'Invitation Only'),
            ('b2c', 'Self-Registration'),
        ],
        string='Portal Access Mode',
        default='b2c',
        config_parameter='auth_signup.invitation_scope')
    auth_signup_template_user_id = fields.Many2one(
        'res.users',
        string='Template user for new users created through signup',
        config_parameter='base.template_portal_user_id')
