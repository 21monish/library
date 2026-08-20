import hashlib

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError


ALLOWED_IMAGE_TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}


def validate_image_upload(upload):
    if upload.size > settings.ASSET_UPLOAD_MAX_BYTES:
        limit = settings.ASSET_UPLOAD_MAX_BYTES // (1024 * 1024)
        raise ValidationError(f'Image must be {limit} MB or smaller.')
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError('Use a JPEG, PNG, or WebP image.')


def upload_public_image(upload, folder):
    """Save an uploaded image in Django media storage and return its URL."""
    validate_image_upload(upload)
    content_type = upload.content_type.lower()
    extension = ALLOWED_IMAGE_TYPES[content_type]
    digest = hashlib.sha256(upload.read()).hexdigest()[:24]
    upload.seek(0)
    object_path = f'{folder}/{digest}{extension}'

    try:
        if default_storage.exists(object_path):
            saved_path = object_path
        else:
            saved_path = default_storage.save(object_path, upload)
        return default_storage.url(saved_path).replace('\\', '/')
    except Exception as exc:
        raise ValidationError(f'Asset upload failed: {exc}') from exc
