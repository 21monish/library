from django.db import migrations, models


ROLE_DEFAULTS = {
    'student': (True, False, False, False),
    'teacher': (True, False, False, False),
    'library': (True, True, True, True),
    'superadmin': (True, True, True, True),
}


def populate_role_permissions(apps, schema_editor):
    Profile = apps.get_model('catalog', 'Profile')
    for profile in Profile.objects.all().iterator():
        values = ROLE_DEFAULTS.get(profile.role, ROLE_DEFAULTS['student'])
        profile.can_view, profile.can_add, profile.can_change, profile.can_delete = values
        profile.save(update_fields=['can_view', 'can_add', 'can_change', 'can_delete'])


class Migration(migrations.Migration):
    dependencies = [('catalog', '0014_optimize_generated_cover_urls')]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='can_view',
            field=models.BooleanField(default=True, help_text='May open staff record screens within the assigned role.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='can_add',
            field=models.BooleanField(default=False, help_text='May create records within the assigned role.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='can_change',
            field=models.BooleanField(default=False, help_text='May edit records and run update workflows within the assigned role.'),
        ),
        migrations.AddField(
            model_name='profile',
            name='can_delete',
            field=models.BooleanField(default=False, help_text='May permanently delete records within the assigned role.'),
        ),
        migrations.RunPython(populate_role_permissions, migrations.RunPython.noop),
    ]
