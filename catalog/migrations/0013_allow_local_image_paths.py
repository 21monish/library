from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0012_ai_generated_book_covers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='book',
            name='cover_url',
            field=models.CharField(
                blank=True,
                help_text='Local asset path or public image URL.',
                max_length=700,
            ),
        ),
        migrations.AlterField(
            model_name='profile',
            name='photo_url',
            field=models.CharField(
                blank=True,
                help_text='Local asset path or public image URL.',
                max_length=700,
            ),
        ),
    ]
