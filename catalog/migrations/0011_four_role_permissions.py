from django.db import migrations, models


LIBRARY_GROUP_NAME = 'Library In-charge'


def normalize_roles(apps, schema_editor):
    Profile = apps.get_model('catalog', 'Profile')
    Group = apps.get_model('auth', 'Group')
    library_group, _ = Group.objects.get_or_create(name=LIBRARY_GROUP_NAME)

    Profile.objects.filter(role='admin').update(role='library')
    Profile.objects.filter(role='super_admin').update(role='superadmin')

    for profile in Profile.objects.select_related('user'):
        user = profile.user
        if user.is_superuser and profile.role != 'superadmin':
            profile.role = 'superadmin'
            profile.save(update_fields=['role'])
        user.is_staff = profile.role in {'library', 'superadmin'}
        user.is_superuser = profile.role == 'superadmin'
        user.save(update_fields=['is_staff', 'is_superuser'])
        if profile.role == 'library':
            user.groups.add(library_group)
        else:
            user.groups.remove(library_group)


def reverse_roles(apps, schema_editor):
    Profile = apps.get_model('catalog', 'Profile')
    Profile.objects.filter(role='library').update(role='admin')
    Profile.objects.filter(role='superadmin').update(role='super_admin')


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0010_penaltytransaction'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(
                choices=[
                    ('student', 'Student'),
                    ('teacher', 'Teacher'),
                    ('library', 'Library In-charge'),
                    ('superadmin', 'Superadmin'),
                ],
                default='student',
                max_length=20,
            ),
        ),
        migrations.RunPython(normalize_roles, reverse_roles),
    ]
