"""Who may manage which events (SDD BR-08).

Only active officers of the organizing organization, or an Admin, can manage
that organization's events and see its participants.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Organization, OrganizationMember


def officer_organizations(user):
    """Active organizations this user may manage events for."""
    if not user.is_authenticated:
        return Organization.objects.none()
    orgs = Organization.objects.filter(is_active=True)
    if user.is_admin_role:
        return orgs
    return orgs.filter(
        memberships__student__user=user,
        memberships__member_role=OrganizationMember.Role.OFFICER,
        memberships__is_active=True,
    ).distinct()


def is_organizer(user):
    return user.is_authenticated and (user.is_admin_role or officer_organizations(user).exists())


def can_manage_event(user, event):
    return user.is_authenticated and (
        user.is_admin_role or officer_organizations(user).filter(pk=event.organization_id).exists()
    )


def organizer_required(view_func):
    """Logged-in Admins and active officers only; everyone else gets a 403."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_organizer(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper
