"""Central role and access rules for Shelfwise.

Keep authorization decisions here so the public workspace, circulation service,
forms, and templates all use the same four-role policy.
"""

from django.contrib.auth.models import Group


STUDENT = 'student'
TEACHER = 'teacher'
LIBRARY = 'library'
SUPERADMIN = 'superadmin'
LIBRARY_GROUP_NAME = 'Library In-charge'

BORROWER_ROLES = (STUDENT, TEACHER)
STAFF_ROLES = (LIBRARY, SUPERADMIN)
CRUD_ACTIONS = ('view', 'add', 'change', 'delete')
ROLE_CRUD_DEFAULTS = {
    STUDENT: {'can_view': True, 'can_add': False, 'can_change': False, 'can_delete': False},
    TEACHER: {'can_view': True, 'can_add': False, 'can_change': False, 'can_delete': False},
    LIBRARY: {'can_view': True, 'can_add': True, 'can_change': True, 'can_delete': True},
    SUPERADMIN: {'can_view': True, 'can_add': True, 'can_change': True, 'can_delete': True},
}
LEGACY_ROLE_MAP = {
    'admin': LIBRARY,
    'super_admin': SUPERADMIN,
}


def get_user_role(user):
    """Return a normalized role, including compatibility during migration."""
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return SUPERADMIN
    role = getattr(getattr(user, 'profile', None), 'role', STUDENT)
    return LEGACY_ROLE_MAP.get(role, role)


def is_superadmin(user):
    return get_user_role(user) == SUPERADMIN


def is_library_staff(user):
    return get_user_role(user) in STAFF_ROLES


def has_crud_permission(user, action):
    """Apply an explicit CRUD grant inside the ceiling imposed by a role."""
    if action not in CRUD_ACTIONS or not user or not user.is_authenticated:
        return False
    if is_superadmin(user):
        return True
    if not is_library_staff(user):
        return False
    return bool(getattr(getattr(user, 'profile', None), f'can_{action}', False))


def set_role_permission_defaults(profile, role):
    """Reset a profile to the safe permission preset for a role."""
    defaults = ROLE_CRUD_DEFAULTS[LEGACY_ROLE_MAP.get(role, role)]
    for field, value in defaults.items():
        setattr(profile, field, value)
    return profile


def can_manage_member(actor, member):
    """Library staff manage borrowers; superadmins manage every account."""
    if is_superadmin(actor):
        return True
    return is_library_staff(actor) and get_user_role(member) in BORROWER_ROLES


def sync_user_role(user, role):
    """Synchronize Django staff flags and groups with the assigned app role."""
    role = LEGACY_ROLE_MAP.get(role, role)
    user.is_staff = role in STAFF_ROLES
    user.is_superuser = role == SUPERADMIN
    user.save(update_fields=['is_staff', 'is_superuser'])

    # Roles are authoritative: a borrower must never keep old staff grants.
    user.groups.clear()
    user.user_permissions.clear()
    if role == LIBRARY:
        group = Group.objects.filter(name=LIBRARY_GROUP_NAME).first()
        if group:
            user.groups.add(group)
    return user
