from __future__ import annotations

from inphms.orm import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    google_key = fields.Char("Google AI API key", store=True, readonly=False)
    google_key_enabled = fields.Boolean("Enable custom Google API key", store=False)
    
    openai_key = fields.Char("OpenAI API key", store=True, readonly=False)
    openai_key_enabled = fields.Boolean("Enable custom OpenAI API key", store=False)

    cloudflare_account_id = fields.Char("Account ID", config_parameter="ai.cloudflare_account_id")
    cloudflare_api_token = fields.Char("Token", config_parameter="ai.cloudflare_api_token")
    cloudflare_ai_enabled = fields.Boolean("Use Cloudflare AI", config_parameter="ai.use_cloudflare_ai")
