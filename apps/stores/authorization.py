"""StoreMembership-based merchant-dashboard authorization.

This module is the single place that decides "may this User act on this
Store's merchant dashboard, and with which permissions." It replaces the
historical, tenant-blind ``user.is_staff`` check that
``apps.dashboard.decorators.staff_required`` used on its own (see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §10.2/§11.1 — this was
the explicitly recorded, highest-priority gap: any ``is_staff=True`` account
could reach *any* Store's ``/admin-panel/`` once Host-based Store resolution
picked that Store, because nothing checked *which* Store the user actually
belonged to).

Authorization here is layered on top of, not a replacement for, tenant
resolution (``apps.stores.resolution``): resolution decides *which* Store a
request is for; this module decides *whether* the requesting User may act on
that Store, and *what* they may do. Neither layer substitutes for the other.

Only an ``ACTIVE`` ``StoreMembership`` row for the exact Store in question
grants access — never ``is_staff``, ``is_superuser``, membership in a
*different* Store, or an ``INVITED``/``REVOKED`` row.
"""

from .models import StoreMembership

Role = StoreMembership.Role

# ---------------------------------------------------------------------------
# Permission registry
# ---------------------------------------------------------------------------

CATALOG = "catalog"
ORDERS = "orders"
CUSTOMERS = "customers"
CONTENT = "content"
SETTINGS = "settings"
REPORTS = "reports"
MEMBERSHIP = "membership"

ALL_PERMISSIONS = frozenset(
    {CATALOG, ORDERS, CUSTOMERS, CONTENT, SETTINGS, REPORTS, MEMBERSHIP}
)

#: What each role may do. Deliberately explicit and centralized — no view
#: or template should hardcode a role name to decide what it can show, only
#: ``user_has_permission``. See the master reference doc §10.3 for the
#: target role list this mirrors (OWNER/ADMINISTRATOR/CATALOG/ORDER/
#: CONTENT/REPORTING); this is the first PR to give those roles real
#: enforced meaning instead of only existing as ``StoreMembership.Role``
#: choices.
ROLE_PERMISSIONS = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMINISTRATOR: frozenset(
        {CATALOG, ORDERS, CUSTOMERS, CONTENT, SETTINGS, REPORTS}
    ),
    Role.CATALOG_MANAGER: frozenset({CATALOG, REPORTS}),
    Role.ORDER_MANAGER: frozenset({ORDERS, CUSTOMERS, REPORTS}),
    Role.CONTENT_EDITOR: frozenset({CONTENT}),
    Role.ANALYST: frozenset({REPORTS}),
}


def get_active_membership(user, store):
    """The user's ACTIVE ``StoreMembership`` for ``store``, or ``None``.

    Returns ``None`` for an unauthenticated user, a ``None`` store, a
    membership in a *different* Store, or a membership whose status is
    ``INVITED``/``REVOKED`` — an inactive/rejected/expired membership must
    never grant access. Exactly one row can ever match, since
    ``StoreMembership`` enforces ``uniq_membership_per_store_user``.
    """
    if store is None or user is None or not getattr(user, "is_authenticated", False):
        return None
    return StoreMembership.objects.filter(
        store=store, user=user, status=StoreMembership.MembershipStatus.ACTIVE
    ).first()


def user_can_access_dashboard(user, store):
    """Whether ``user`` may open ``store``'s merchant dashboard at all.

    Any active membership, regardless of role, grants baseline access — an
    ``ANALYST`` may sign in and see report pages, for instance. Fine-grained
    per-action gating is ``user_has_permission``.
    """
    return get_active_membership(user, store) is not None


def user_has_permission(user, store, permission):
    """Whether ``user``'s active membership in ``store`` grants ``permission``.

    ``permission`` must be one of the module-level constants above.
    """
    membership = get_active_membership(user, store)
    if membership is None:
        return False
    return permission in ROLE_PERMISSIONS.get(membership.role, frozenset())
