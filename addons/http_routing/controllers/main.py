
from inphms.server import route
from inphms.server.utils import request
from inphms.addons.web.controllers.home import Home
from inphms.addons.web.controllers.session import Session
from inphms.addons.web.controllers.webclient import WebClient


class Routing(Home):

    @route('/website/translations', type='http', auth="public", website=True, readonly=True, sitemap=False)
    def get_website_translations(self, hash=None, lang=None, mods=None):
        IrHttp = request.env['ir.http'].sudo()
        modules = IrHttp.get_translation_frontend_modules()
        if mods:
            modules += mods.split(',')
        return WebClient().translations(hash, mods=','.join(modules), lang=lang)


class SessionWebsite(Session):

    @route('/web/session/logout', website=True, multilang=False, sitemap=False)
    def logout(self, redirect='/inphms'):
        return super().logout(redirect=redirect)
