from django.db import migrations


COVER_NAMES = ('foundation-ai', 'the-hobbit-ai', '1984-ai', 'sapiens-ai')


def use_webp_covers(apps, schema_editor):
    Book = apps.get_model('catalog', 'Book')
    for name in COVER_NAMES:
        Book.objects.filter(
            cover_url=f'/static/catalog/book-covers/{name}.png',
        ).update(cover_url=f'/static/catalog/book-covers/{name}.webp')


def use_png_covers(apps, schema_editor):
    Book = apps.get_model('catalog', 'Book')
    for name in COVER_NAMES:
        Book.objects.filter(
            cover_url=f'/static/catalog/book-covers/{name}.webp',
        ).update(cover_url=f'/static/catalog/book-covers/{name}.png')


class Migration(migrations.Migration):
    dependencies = [('catalog', '0013_allow_local_image_paths')]
    operations = [migrations.RunPython(use_webp_covers, use_png_covers)]
