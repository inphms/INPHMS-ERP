from __future__ import annotations

from inphms.orm.fields import Command
from inphms.orm import models, api


class UsersMultiCompany(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        group_multi_company_id = self.env['ir.model.data']._xmlid_to_res_id(
            'base.group_multi_company', raise_if_not_found=False)
        if group_multi_company_id:
            for user in users:
                if len(user.company_ids) <= 1 and group_multi_company_id in user.group_ids.ids:
                    user.write({'group_ids': [Command.unlink(group_multi_company_id)]})
                elif len(user.company_ids) > 1 and group_multi_company_id not in user.group_ids.ids:
                    user.write({'group_ids': [Command.link(group_multi_company_id)]})
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'company_ids' not in vals:
            return res
        group_multi_company_id = self.env['ir.model.data']._xmlid_to_res_id(
            'base.group_multi_company', raise_if_not_found=False)
        if group_multi_company_id:
            for user in self:
                if len(user.company_ids) <= 1 and group_multi_company_id in user.group_ids.ids:
                    user.write({'group_ids': [Command.unlink(group_multi_company_id)]})
                elif len(user.company_ids) > 1 and group_multi_company_id not in user.group_ids.ids:
                    user.write({'group_ids': [Command.link(group_multi_company_id)]})
        return res

    @api.model
    def new(self, values=None, origin=None, ref=None):
        if values is None:
            values = {}
        user = super().new(values=values, origin=origin, ref=ref)
        group_multi_company_id = self.env['ir.model.data']._xmlid_to_res_id(
            'base.group_multi_company', raise_if_not_found=False)
        if group_multi_company_id:
            if len(user.company_ids) <= 1 and group_multi_company_id in user.group_ids.ids:
                user.update({'group_ids': [Command.unlink(group_multi_company_id)]})
            elif len(user.company_ids) > 1 and group_multi_company_id not in user.group_ids.ids:
                user.update({'group_ids': [Command.link(group_multi_company_id)]})
        return user
