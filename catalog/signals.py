from django.apps import apps as django_apps
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .permissions import LIBRARY, LIBRARY_GROUP_NAME


@receiver(post_migrate)
def configure_library_role(sender, **kwargs):
    """Build the operational permission group after permissions exist."""
    if sender.name != 'catalog':
        return
    group, _ = Group.objects.get_or_create(name=LIBRARY_GROUP_NAME)
    editable_models = {'author', 'genre', 'book', 'bookinstance'}
    view_only_models = {
        'loan', 'penalty', 'penaltytransaction', 'reservation',
        'notification', 'scanaudit',
    }
    permissions = Permission.objects.filter(
        content_type__app_label='catalog',
    ).filter(
        content_type__model__in=editable_models,
        codename__regex=r'^(add|change|delete|view)_',
    ) | Permission.objects.filter(
        content_type__app_label='catalog',
        content_type__model__in=view_only_models,
        codename__startswith='view_',
    )
    group.permissions.set(permissions.distinct())

    User = django_apps.get_model('auth', 'User')
    group.user_set.add(*User.objects.filter(profile__role=LIBRARY))
