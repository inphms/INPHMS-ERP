from __future__ import annotations

from inphms.orm import models

##################################################################
# IMPORTANT: this must be the first model declared in the module #
##################################################################
class Base(models.AbstractModel):
    """ The base model, which is implicitly inherited by all models. """
    _name = 'base'
    _description = 'Base'


class Unknown(models.AbstractModel):
    """
    Abstract model used as a substitute for relational fields with an unknown
    comodel.
    """
    _name = '_unknown'
    _description = 'Unknown'
