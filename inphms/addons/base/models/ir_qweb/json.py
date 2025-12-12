from __future__ import annotations

from inphms.tools import json
from .content import QwebContent


class QwebJSON(json.JSON):
    def dumps(self, *args, **kwargs):
        prev_default = kwargs.pop('default', lambda obj: obj)
        return super().dumps(*args, **kwargs, default=(
            lambda obj: prev_default(str(obj) if isinstance(obj, QwebContent) else obj)
        ))


qwebJSON = QwebJSON()
