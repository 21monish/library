from django.db import migrations


COVERS = {
    'Foundation': '/static/catalog/book-covers/foundation-ai.png',
    'The Hobbit': '/static/catalog/book-covers/the-hobbit-ai.png',
    '1984': '/static/catalog/book-covers/1984-ai.png',
    'Sapiens': '/static/catalog/book-covers/sapiens-ai.png',
    'Sapiens: A Brief History of Humankind': '/static/catalog/book-covers/sapiens-ai.png',
}


def add_generated_covers(apps, schema_editor):
    Book = apps.get_model('catalog', 'Book')
    for title, cover_url in COVERS.items():
        Book.objects.filter(title=title).update(cover_url=cover_url)


def remove_generated_covers(apps, schema_editor):
    Book = apps.get_model('catalog', 'Book')
    for title, cover_url in COVERS.items():
        Book.objects.filter(title=title, cover_url=cover_url).update(cover_url='')


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_four_role_permissions'),
    ]

    operations = [
        migrations.RunPython(add_generated_covers, remove_generated_covers),
    ]
