from __future__ import annotations

from inphms.addons.mail.tools.alias_error import AliasError
from inphms.orm import models
from inphms.tools import email_normalize, _
from inphms.tools.mailutils import decode_message_header


class Base(models.AbstractModel):
    _inherit = 'base'

    def _alias_get_error(self, message, message_dict, alias):
        if alias.alias_contact == 'employees':
            email_from = decode_message_header(message, 'From')
            email_address = email_normalize(email_from, strict=False)
            employee = self.env['hr.employee'].search([('work_email', 'ilike', email_address)], limit=1)
            if not employee:
                employee = self.env['hr.employee'].search([('user_id.email', 'ilike', email_address)], limit=1)
            if not employee:
                return AliasError('error_hr_employee_restricted', _('restricted to employees'))
            return False
        return super()._alias_get_error(message, message_dict, alias)
