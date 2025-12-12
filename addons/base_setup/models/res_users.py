from __future__ import annotations

from inphms.exceptions import UserError
from inphms.orm import models, api
from inphms.tools import parse_contact_from_email

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def web_create_users(self, emails):
        emails_normalized = [parse_contact_from_email(email)[1] for email in emails]

        if 'email_normalized' not in self._fields:
            raise UserError(self.env._("You have to install the Talks application to use this feature."))

        # Reactivate already existing users if needed
        deactivated_users = self.with_context(active_test=False).search([
            ('active', '=', False),
            '|', ('login', 'in', emails + emails_normalized), ('email_normalized', 'in', emails_normalized)])
        for user in deactivated_users:
            user.active = True
        done = deactivated_users.mapped('email_normalized')

        new_emails = set(emails) - set(deactivated_users.mapped('email'))

        # Process new email addresses : create new users
        for email in new_emails:
            name, email_normalized = parse_contact_from_email(email)
            if email_normalized in done:
                continue
            default_values = {'login': email_normalized, 'name': name or email_normalized, 'email': email_normalized, 'active': True}
            user = self.with_context(signup_valid=True).create(default_values)

        return True