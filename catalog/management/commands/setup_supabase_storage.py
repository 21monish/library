from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.storage import supabase_client


class Command(BaseCommand):
    help = 'Create or verify the public Supabase bucket used for library images.'

    def handle(self, *args, **options):
        try:
            client = supabase_client()
            bucket_name = settings.SUPABASE_STORAGE_BUCKET
            buckets = client.storage.list_buckets()
            existing = next((bucket for bucket in buckets if bucket.name == bucket_name), None)
            if existing is None:
                client.storage.create_bucket(
                    bucket_name,
                    options={
                        'public': True,
                        'allowed_mime_types': ['image/jpeg', 'image/png', 'image/webp'],
                        'file_size_limit': settings.ASSET_UPLOAD_MAX_BYTES,
                    },
                )
                self.stdout.write(self.style.SUCCESS(f'Created public bucket: {bucket_name}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Bucket is ready: {bucket_name}'))
        except Exception as exc:
            raise CommandError(f'Supabase Storage setup failed: {exc}') from exc
