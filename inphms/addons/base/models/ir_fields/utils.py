from typing import NamedTuple

from inphms.tools import LazyTranslate

_lt = LazyTranslate(__name__)

REFERENCING_FIELDS = {None, 'id', '.id'}

# these lazy translations promise translations for ['yes', 'no', 'true', 'false']
BOOLEAN_TRANSLATIONS = (
    _lt('yes'),
    _lt('no'),
    _lt('true'),
    _lt('false')
)


def only_ref_fields(record):
    return {k: v for k, v in record.items() if k in REFERENCING_FIELDS}

def exclude_ref_fields(record):
    return {k: v for k, v in record.items() if k not in REFERENCING_FIELDS}


################
# CLASS HELPER #
################
class FakeField(NamedTuple):
    comodel_name: str
    name: str

class ImportWarning(Warning):
    """ Used to send warnings upwards the stack during the import process """
    pass