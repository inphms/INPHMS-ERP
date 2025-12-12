
from inphms.orm import models
from inphms.addons.base.models.res_lang import LangDataDict


class ResLang(models.Model):
    _inherit = "res.lang"

    def _get_frontend(self) -> LangDataDict:
        """ Return the available languages for current request
        :return: LangDataDict({code: LangData})
        """
        return self._get_active_by('code')
