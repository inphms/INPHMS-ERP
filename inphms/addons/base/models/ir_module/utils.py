from __future__ import annotations
import logging
import functools
import typing
import os
import shutil

from docutils import nodes
from docutils.writers.html4css1 import Writer
from docutils.transforms import Transform, writer_aux

from inphms.server.utils import request
from inphms.tools import _
from inphms.exceptions import ValidationError, AccessDenied, UserError, MissingDependency

T = typing.TypeVar('T')
_logger = logging.getLogger(__name__)


ACTION_DICT = {
    'view_mode': 'form',
    'res_model': 'base.module.upgrade',
    'target': 'new',
    'type': 'ir.actions.act_window',
}

STATES = [
    ('uninstallable', 'Uninstallable'),
    ('uninstalled', 'Not Installed'),
    ('installed', 'Installed'),
    ('to upgrade', 'To be upgraded'),
    ('to remove', 'To be removed'),
    ('to install', 'To be installed'),
]

XML_DECLARATION = (
    '<?xml version='.encode('utf-8'),
    '<?xml version='.encode('utf-16-be'),
    '<?xml version='.encode('utf-16-le'),
)

DEP_STATES = STATES + [('unknown', 'Unknown')]


def backup(path, raise_exception=True):
    path = os.path.normpath(path)
    if not os.path.exists(path):
        if not raise_exception:
            return None
        raise OSError('path does not exists')
    cnt = 1
    while True:
        bck = '%s~%d' % (path, cnt)
        if not os.path.exists(bck):
            shutil.move(path, bck)
            return bck
        cnt += 1

def assert_log_admin_access(method: T, /) -> T:
    """Decorator checking that the calling user is an administrator, and logging the call.

    Raises an AccessDenied error if the user does not have administrator privileges, according
    to `user._is_admin()`.
    """
    @functools.wraps(method)
    def check_and_log(self, *args, **kwargs):
        user = self.env.user
        origin = request.httprequest.remote_addr if request else 'n/a'
        log_data = (method.__name__, self.sudo().mapped('display_name'), user.login, user.id, origin)
        if not self.env.is_admin():
            _logger.warning('DENY access to module.%s on %s to user %s ID #%s via %s', *log_data)
            raise AccessDenied()
        _logger.info('ALLOW access to module.%s on %s to user %s #%s via %s', *log_data)
        return method(self, *args, **kwargs)
    return check_and_log


################
# CLASS HELPER #
################
class MyWriter(Writer):
    """
    Custom docutils html4ccs1 writer that doesn't add the warnings to the
    output document.
    """
    def get_transforms(self):
        return [MyFilterMessages, writer_aux.Admonitions]


class MyFilterMessages(Transform):
    """
    Custom docutils transform to remove `system message` for a document and
    generate warnings.

    (The standard filter removes them based on some `report_level` passed in
    the `settings_override` dictionary, but if we use it, we can't see them
    and generate warnings.)
    """
    default_priority = 870

    def apply(self):
        # Use `findall()` if available (docutils >= 0.20), otherwise fallback to `traverse()`.
        # This ensures compatibility across environments with different docutils versions.
        if hasattr(self.document, 'findall'):
            nodes_iter = self.document.findall(nodes.system_message)
        else:
            nodes_iter = self.document.traverse(nodes.system_message)

        for node in nodes_iter:
            _logger.warning("docutils' system message present: %s", str(node))
            node.parent.remove(node)
