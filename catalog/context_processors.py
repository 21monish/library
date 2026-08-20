from django.conf import settings

from .permissions import CRUD_ACTIONS, get_user_role, has_crud_permission, is_library_staff, is_superadmin


def notification_context(request):
    if not request.user.is_authenticated:
        return {
            'unread_notification_count': 0,
            'loan_policy': settings.LOAN_DAYS_BY_ROLE,
            'penalty_per_day': settings.PENALTY_PER_DAY,
            'current_role': None,
            'is_library_admin': False,
            'is_superadmin': False,
            'crud_permissions': {action: False for action in CRUD_ACTIONS},
        }
    return {
        'unread_notification_count': request.user.notifications.filter(
            is_read=False
        ).count(),
        'loan_policy': settings.LOAN_DAYS_BY_ROLE,
        'penalty_per_day': settings.PENALTY_PER_DAY,
        'current_role': get_user_role(request.user),
        'is_library_admin': is_library_staff(request.user),
        'is_superadmin': is_superadmin(request.user),
        'crud_permissions': {
            action: has_crud_permission(request.user, action)
            for action in CRUD_ACTIONS
        },
    }
