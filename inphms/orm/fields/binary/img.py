from __future__ import annotations
import base64
import warnings

from inphms.tools.mimetypes import guess_mimetype
from inphms.exceptions import UserError

from .binary import Binary


class Image(Binary):
    """Encapsulates an image, extending :class:`Binary`.

    If image size is greater than the ``max_width``/``max_height`` limit of pixels, the image will be
    resized to the limit by keeping aspect ratio.

    :param int max_width: the maximum width of the image (default: ``0``, no limit)
    :param int max_height: the maximum height of the image (default: ``0``, no limit)
    :param bool verify_resolution: whether the image resolution should be verified
        to ensure it doesn't go over the maximum image resolution (default: ``True``).
        See :class:`inphms.tools.image.ImageProcess` for maximum image resolution (default: ``50e6``).

    .. note::

        If no ``max_width``/``max_height`` is specified (or is set to 0) and ``verify_resolution`` is False,
        the field content won't be verified at all and a :class:`Binary` field should be used.
    """
    max_width = 0
    max_height = 0
    verify_resolution = True

    def setup(self, model):
        super().setup(model)
        if not model._abstract and not model._log_access:
            warnings.warn(f"Image field {self} requires the model to have _log_access = True", stacklevel=1)

    def create(self, record_values):
        new_record_values = []
        for record, value in record_values:
            new_value = self._image_process(value, record.env)
            new_record_values.append((record, new_value))
            # when setting related image field, keep the unprocessed image in
            # cache to let the inverse method use the original image; the image
            # will be resized once the inverse has been applied
            cache_value = self.convert_to_cache(value if self.related else new_value, record)
            self._update_cache(record, cache_value)
        super().create(new_record_values)

    def write(self, records, value):
        try:
            new_value = self._image_process(value, records.env)
        except UserError:
            if not any(records._ids):
                # Some crap is assigned to a new record. This can happen in an
                # onchange, where the client sends the "bin size" value of the
                # field instead of its full value (this saves bandwidth). In
                # this case, we simply don't assign the field: its value will be
                # taken from the records' origin.
                return
            raise

        super().write(records, new_value)
        cache_value = self.convert_to_cache(value if self.related else new_value, records)
        self._update_cache(records, cache_value, dirty=True)

    def _inverse_related(self, records):
        super()._inverse_related(records)
        if not (self.max_width and self.max_height):
            return
        # the inverse has been applied with the original image; now we fix the
        # cache with the resized value
        for record in records:
            value = self._process_related(record[self.name], record.env)
            self._update_cache(record, value, dirty=True)

    def _image_process(self, value, env):
        if self.readonly and not self.max_width and not self.max_height:
            # no need to process images for computed fields, or related fields
            return value
        try:
            img = base64.b64decode(value or '') or False
        except Exception as e:
            raise UserError(env._("Image is not encoded in base64.")) from e

        if img and guess_mimetype(img, '') == 'image/webp':
            if not self.max_width and not self.max_height:
                return value
            # Fetch resized version.
            Attachment = env['ir.attachment']
            checksum = Attachment._compute_checksum(img)
            origins = Attachment.search([
                ['id', '!=', False],  # No implicit condition on res_field.
                ['checksum', '=', checksum],
            ])
            if origins:
                origin_ids = [attachment.id for attachment in origins]
                resized_domain = [
                    ['id', '!=', False],  # No implicit condition on res_field.
                    ['res_model', '=', 'ir.attachment'],
                    ['res_id', 'in', origin_ids],
                    ['description', '=', 'resize: %s' % max(self.max_width, self.max_height)],
                ]
                resized = Attachment.sudo().search(resized_domain, limit=1)
                if resized:
                    # Fallback on non-resized image (value).
                    return resized.datas or value
            return value

        # delay import of image_process until this point
        from inphms.tools.imageutils import image_process  # noqa: PLC0415
        return base64.b64encode(image_process(img,
            size=(self.max_width, self.max_height),
            verify_resolution=self.verify_resolution,
        ) or b'') or False

    def _process_related(self, value, env):
        """Override to resize the related value before saving it on self."""
        try:
            return self._image_process(super()._process_related(value, env), env)
        except UserError:
            # Avoid the following `write` to fail if the related image was saved
            # invalid, which can happen for pre-existing databases.
            return False
