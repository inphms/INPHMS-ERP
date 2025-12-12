from __future__ import annotations

from .basestring import BaseString

class Text(BaseString):
    """ Very similar to :class:`Char` but used for longer contents, does not
        have a size and usually displayed as a multiline text box.

        :param translate: enable the translation of the field's values; use
            ``translate=True`` to translate field values as a whole; ``translate``
            may also be a callable such that ``translate(callback, value)``
            translates ``value`` by using ``callback(term)`` to retrieve the
            translation of terms.
        :type translate: bool or callable
    """
    type = 'text'
    _column_type = ('text', 'text')
