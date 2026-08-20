import hashlib
import os
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.exceptions import ImproperlyConfigured, ValidationError
from supabase import Client, create_client


ALLOWED_IMAGE_TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}


@lru_cache(maxsize=1)
def supabase_client():
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise ImproperlyConfigured(
            'Set SUPABASE_URL and a rotated SUPABASE_SERVICE_KEY to upload assets.'
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def validate_image_upload(upload):
    if upload.size > settings.ASSET_UPLOAD_MAX_BYTES:
        limit = settings.ASSET_UPLOAD_MAX_BYTES // (1024 * 1024)
        raise ValidationError(f'Image must be {limit} MB or smaller.')
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError('Use a JPEG, PNG, or WebP image.')


def upload_public_image(upload, folder):
    """Upload an image and return its public URL; use local media in development."""
    validate_image_upload(upload)
    content_type = upload.content_type.lower()
    extension = ALLOWED_IMAGE_TYPES[content_type]
    digest = hashlib.sha256(upload.read()).hexdigest()[:24]
    upload.seek(0)
    object_path = f'{folder}/{digest}{extension}'

    if settings.DEBUG and not settings.SUPABASE_SERVICE_KEY:
        saved_path = default_storage.save(object_path, upload)
        return f'{settings.MEDIA_URL}{saved_path}'.replace('\\', '/')

    try:
        bucket = supabase_client().storage.from_(settings.SUPABASE_STORAGE_BUCKET)
        bucket.upload(
            path=object_path,
            file=upload.read(),
            file_options={
                'content-type': content_type,
                'cache-control': '31536000',
                'upsert': 'true',
            },
        )
        return bucket.get_public_url(object_path)
    except Exception as exc:
        raise ValidationError(f'Asset upload failed: {exc}') from exc
