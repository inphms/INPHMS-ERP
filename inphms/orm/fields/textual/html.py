from __future__ import annotations
import logging

from difflib import unified_diff
from operator import attrgetter
from markupsafe import Markup, escape as markup_escape

from .basestring import BaseString
from inphms.tools import html_translate, html_normalize, html_sanitize, html2plaintext, plaintext2html, is_html_empty
from ..field import _logger
from inphms.exceptions import UserError
from inphms.netsvc import COLOR_PATTERN, DEFAULT, GREEN, RED, ColoredFormatter


class Html(BaseString):
    """ Encapsulates an html code content.

        :param bool sanitize: whether value must be sanitized (default: ``True``)
        :param bool sanitize_overridable: whether the sanitation can be bypassed by
            the users part of the `base.group_sanitize_override` group (default: ``False``)
        :param bool sanitize_tags: whether to sanitize tags
            (only a white list of attributes is accepted, default: ``True``)
        :param bool sanitize_attributes: whether to sanitize attributes
            (only a white list of attributes is accepted, default: ``True``)
        :param bool sanitize_style: whether to sanitize style attributes (default: ``False``)
        :param bool sanitize_conditional_comments: whether to kill conditional comments. (default: ``True``)
        :param bool sanitize_output_method: whether to sanitize using html or xhtml (default: ``html``)
        :param bool strip_style: whether to strip style attributes
            (removed and therefore not sanitized, default: ``False``)
        :param bool strip_classes: whether to strip classes attributes (default: ``False``)
    """
    type = 'html'
    _column_type = ('text', 'text')

    sanitize: bool = True                     # whether value must be sanitized
    sanitize_overridable: bool = False        # whether the sanitation can be bypassed by the users part of the `base.group_sanitize_override` group
    sanitize_tags: bool = True                # whether to sanitize tags (only a white list of attributes is accepted)
    sanitize_attributes: bool = True          # whether to sanitize attributes (only a white list of attributes is accepted)
    sanitize_style: bool = False              # whether to sanitize style attributes
    sanitize_form: bool = True                # whether to sanitize forms
    sanitize_conditional_comments: bool = True  # whether to kill conditional comments. Otherwise keep them but with their content sanitized.
    sanitize_output_method: str = 'html'      # whether to sanitize using html or xhtml
    strip_style: bool = False                 # whether to strip style attributes (removed and therefore not sanitized)
    strip_classes: bool = False               # whether to strip classes attributes

    def _get_attrs(self, model_class, name):
        # called by _setup_attrs__(), working together with BaseString._setup_attrs__()
        attrs = super()._get_attrs(model_class, name)
        # Shortcut for common sanitize options
        # Outgoing and incoming emails should not be sanitized with the same options.
        # e.g. conditional comments: no need to keep conditional comments for incoming emails,
        # we do not need this Microsoft Outlook client feature for emails displayed Inphms's web client.
        # While we need to keep them in mail templates and mass mailings, because they could be rendered in Outlook.
        if attrs.get('sanitize') == 'email_outgoing':
            attrs['sanitize'] = True
            attrs.update({key: value for key, value in {
                'sanitize_tags': False,
                'sanitize_attributes': False,
                'sanitize_conditional_comments': False,
                'sanitize_output_method': 'xml',
            }.items() if key not in attrs})
        # Translated sanitized html fields must use html_translate or a callable.
        # `elif` intended, because HTML fields with translate=True and sanitize=False
        # where not using `html_translate` before and they must remain without `html_translate`.
        # Otherwise, breaks `--test-tags .test_render_field`, for instance.
        elif attrs.get('translate') is True and attrs.get('sanitize', True):
            attrs['translate'] = html_translate
        return attrs

    _related_sanitize = property(attrgetter('sanitize'))
    _related_sanitize_tags = property(attrgetter('sanitize_tags'))
    _related_sanitize_attributes = property(attrgetter('sanitize_attributes'))
    _related_sanitize_style = property(attrgetter('sanitize_style'))
    _related_strip_style = property(attrgetter('strip_style'))
    _related_strip_classes = property(attrgetter('strip_classes'))

    _description_sanitize = property(attrgetter('sanitize'))
    _description_sanitize_tags = property(attrgetter('sanitize_tags'))
    _description_sanitize_attributes = property(attrgetter('sanitize_attributes'))
    _description_sanitize_style = property(attrgetter('sanitize_style'))
    _description_strip_style = property(attrgetter('strip_style'))
    _description_strip_classes = property(attrgetter('strip_classes'))

    def convert_to_column(self, value, record, values=None, validate=True):
        value = self._convert(value, record, validate=validate)
        return super().convert_to_column(value, record, values, validate=False)

    def convert_to_cache(self, value, record, validate=True):
        return self._convert(value, record, validate)

    def _convert(self, value, record, validate):
        if value is None or value is False:
            return None

        if not validate or not self.sanitize:
            return value

        sanitize_vals = {
            'silent': True,
            'sanitize_tags': self.sanitize_tags,
            'sanitize_attributes': self.sanitize_attributes,
            'sanitize_style': self.sanitize_style,
            'sanitize_form': self.sanitize_form,
            'sanitize_conditional_comments': self.sanitize_conditional_comments,
            'output_method': self.sanitize_output_method,
            'strip_style': self.strip_style,
            'strip_classes': self.strip_classes
        }

        if self.sanitize_overridable:
            if record.env.user.has_group('base.group_sanitize_override'):
                return value

            original_value = record[self.name]
            if original_value:
                # Note that sanitize also normalize
                original_value_sanitized = html_sanitize(original_value, **sanitize_vals)
                original_value_normalized = html_normalize(original_value)

                if (
                    not original_value_sanitized  # sanitizer could empty it
                    or original_value_normalized != original_value_sanitized
                ):
                    # The field contains element(s) that would be removed if
                    # sanitized. It means that someone who was part of a group
                    # allowing to bypass the sanitation saved that field
                    # previously.

                    diff = unified_diff(
                        original_value_sanitized.splitlines(),
                        original_value_normalized.splitlines(),
                    )

                    with_colors = isinstance(logging.getLogger().handlers[0].formatter, ColoredFormatter)
                    diff_str = f'The field ({record._description}, {self.string}) will not be editable:\n'
                    for line in list(diff)[2:]:
                        if with_colors:
                            color = {'-': RED, '+': GREEN}.get(line[:1], DEFAULT)
                            diff_str += COLOR_PATTERN % (30 + color, 40 + DEFAULT, line.rstrip() + "\n")
                        else:
                            diff_str += line.rstrip() + '\n'
                    _logger.info(diff_str)

                    raise UserError(record.env._(
                        "The field value you're saving (%(model)s %(field)s) includes content that is "
                        "restricted for security reasons. It is possible that someone "
                        "with higher privileges previously modified it, and you are therefore "
                        "not able to modify it yourself while preserving the content.",
                        model=record._description, field=self.string,
                    ))

        return html_sanitize(value, **sanitize_vals)

    def convert_to_record(self, value, record):
        r = super().convert_to_record(value, record)
        if isinstance(r, bytes):
            r = r.decode()
        return r and Markup(r)

    def convert_to_read(self, value, record, use_display_name=True):
        r = super().convert_to_read(value, record, use_display_name)
        if isinstance(r, bytes):
            r = r.decode()
        return r and Markup(r)

    def get_trans_terms(self, value):
        # ensure the translation terms are stringified, otherwise we can break the PO file
        return list(map(str, super().get_trans_terms(value)))

    escape = staticmethod(markup_escape)
    is_empty = staticmethod(is_html_empty)
    to_plaintext = staticmethod(html2plaintext)
    from_plaintext = staticmethod(plaintext2html)
