from __future__ import annotations

from inphms.exceptions import UserError
from inphms.tools import _

API_URL = "https://api.cloudflare.com/client/v4/accounts"

def get_cloudflare_credentials(env):
    params = env['ir.config_parameter'].sudo()
    if not params.get_param("ai.cloudflare_account_id"):
        return None, None
    account_id = params.get_param("ai.cloudflare_account_id")
    api_token = params.get_param("ai.cloudflare_api_token")
    return account_id, api_token

def prepare_cloudflare(env, llm_model):
    account_id, api_token = get_cloudflare_credentials(env)
    if not account_id or not api_token:
        raise UserError(_('Setup Cloudflare account id and api token to user AI Chat'))
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    api_url = f"{API_URL}/{account_id}/ai/run/{llm_model}"
    return api_url, headers