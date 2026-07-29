"""StoreMembership-based merchant-dashboard authorization.

This module is the single place that decides "may this User act on this
Store's merchant dashboard, and with which permissions." It replaces the
historical, tenant-blind ``user.is_staff`` check that
``apps.dashboard.decorators.staff_required`` used on its own (see
``docs/docs/product/00_PROJECT_MASTER_REFERENCE.md`` §10.2/§11.1 — this was
the explicitly recorded, highest-priority gap: any ``is_staff=True`` account
could reach *any* Store's ``/admin-portal/`` once Host-based Store resolution
picked that Store, because nothing checked *which* Store the user actually
belonged to).

Authorization here is layered on top of, not a replacement for, tenant
resolution (``apps.stores.resolution``): resolution decides *which* Store a
request is for; this module decides *whether* the requesting User may act on
that Store, and *what* they may do. Neither layer substitutes for the other.

Only an ``ACTIVE`` ``StoreMembership`` row for the exact Store in question
grants access — never ``is_staff``, ``is_superuser``, membership in a
*different* Store, or an ``INVITED``/``REVOKED`` row.

Role naming note (Phase 1B): the originating request names roles as
"Owner / Administrator / Manager / Product Manager / Order Manager /
Content Manager / Analyst or Read-Only." Per that same request's own
instruction to reuse existing role names rather than create a duplicate
role system, this maps onto the ``StoreMembership.Role`` choices that
already existed before this PR:

* Owner            -> ``Role.OWNER``
* Administrator     -> ``Role.ADMINISTRATOR`` (also covers the generic
  "Manager" description — full operational access short of ownership-tier
  actions like staff/domain/subscription management)
* Product Manager   -> ``Role.CATALOG_MANAGER``
* Order Manager     -> ``Role.ORDER_MANAGER``
* Content Manager   -> ``Role.CONTENT_EDITOR``
* Analyst/Read-Only -> ``Role.ANALYST``

No new ``Role`` value was added.
"""

from .models import StoreMembership

Role = StoreMembership.Role

# ---------------------------------------------------------------------------
# Permission registry
# ---------------------------------------------------------------------------
#
# Granular permission keys. Some of these (marked "reserved" below) have no
# corresponding view yet — attributes, discounts/coupons, customer editing,
# domain management, and subscription management are not yet implemented as
# merchant-admin features at all (no route exists for them in
# ``apps.dashboard.urls``). Staff/membership management (``STAFF_MANAGE``)
# *is* implemented — see ``apps.stores.services.membership_service`` and
# ``apps.dashboard.views`` staff_* views. Unimplemented keys are still
# defined and given a role mapping here, per the Phase 1B
# role-permission-matrix requirement, so that the day a view for them exists
# it only needs a ``permission_required(...)`` decorator — no new registry
# design.

DASHBOARD_VIEW = "dashboard.view"

PRODUCT_VIEW = "product.view"
PRODUCT_CREATE = "product.create"
PRODUCT_EDIT = "product.edit"
PRODUCT_DELETE = "product.delete"
CATEGORY_MANAGE = "category.manage"
ATTRIBUTE_MANAGE = "attribute.manage"  # reserved — no attribute feature yet
VARIANT_MANAGE = "variant.manage"
INVENTORY_MANAGE = "inventory.manage"
MEDIA_MANAGE = "media.manage"

ORDER_VIEW = "order.view"
ORDER_STATUS_CHANGE = "order.status_change"

CUSTOMER_VIEW = "customer.view"
CUSTOMER_EDIT = "customer.edit"  # reserved — no customer-edit view yet

REPORTS_VIEW = "reports.view"
COUPON_VIEW = "coupon.view"
DISCOUNT_MANAGE = "discount.manage"  # Coupon create/edit/archive (Admin Panel Completion Program checkpoint 2)

RETURN_VIEW = "return.view"
RETURN_MANAGE = "return.manage"  # approve/reject/receive/inspect/complete
REFUND_VIEW = "refund.view"
REFUND_MANAGE = "refund.manage"  # create/execute a refund

AUDIT_LOG_VIEW = "audit.view"

SETTINGS_MANAGE = "settings.manage"
PAYMENT_SETTINGS_MANAGE = "settings.payment"
SMS_SETTINGS_MANAGE = "settings.sms"
CONTENT_MANAGE = "content.manage"

STAFF_MANAGE = "staff.manage"
DOMAIN_MANAGE = "domain.manage"  # reserved — no domain-management UI yet
SUBSCRIPTION_MANAGE = "subscription.manage"  # reserved — no billing UI yet

# Back-compat aliases: the coarse Phase-1 keys these replace. Nothing in
# this codebase reads these anymore (all decorated views moved to the
# granular keys above in the same PR that added them), kept only so an
# external caller importing the old names does not hard-crash.
CATALOG = PRODUCT_VIEW
ORDERS = ORDER_VIEW
CUSTOMERS = CUSTOMER_VIEW
CONTENT = CONTENT_MANAGE
SETTINGS = SETTINGS_MANAGE
REPORTS = REPORTS_VIEW
MEMBERSHIP = STAFF_MANAGE

ALL_PERMISSIONS = frozenset({
    DASHBOARD_VIEW,
    PRODUCT_VIEW, PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE,
    CATEGORY_MANAGE, ATTRIBUTE_MANAGE, VARIANT_MANAGE, INVENTORY_MANAGE, MEDIA_MANAGE,
    ORDER_VIEW, ORDER_STATUS_CHANGE,
    CUSTOMER_VIEW, CUSTOMER_EDIT,
    REPORTS_VIEW, COUPON_VIEW, DISCOUNT_MANAGE,
    RETURN_VIEW, RETURN_MANAGE, REFUND_VIEW, REFUND_MANAGE,
    AUDIT_LOG_VIEW,
    SETTINGS_MANAGE, PAYMENT_SETTINGS_MANAGE, SMS_SETTINGS_MANAGE, CONTENT_MANAGE,
    STAFF_MANAGE, DOMAIN_MANAGE, SUBSCRIPTION_MANAGE,
})

_CATALOG_READ_WRITE = frozenset({
    PRODUCT_VIEW, PRODUCT_CREATE, PRODUCT_EDIT, PRODUCT_DELETE,
    CATEGORY_MANAGE, ATTRIBUTE_MANAGE, VARIANT_MANAGE, INVENTORY_MANAGE, MEDIA_MANAGE,
})
# Order Manager owns Returns/Refunds financial authority (checkpoint 2 §15
# policy) — Catalog Manager deliberately does NOT get REFUND_MANAGE/RETURN_MANAGE.
_ORDER_READ_WRITE = frozenset({
    ORDER_VIEW, ORDER_STATUS_CHANGE, CUSTOMER_VIEW, CUSTOMER_EDIT,
    RETURN_VIEW, RETURN_MANAGE, REFUND_VIEW, REFUND_MANAGE,
})
_CONTENT_READ_WRITE = frozenset({CONTENT_MANAGE, MEDIA_MANAGE})
_OWNER_ONLY = frozenset({STAFF_MANAGE, DOMAIN_MANAGE, SUBSCRIPTION_MANAGE})

#: What each role may do. Deliberately explicit and centralized — no view
#: or template should hardcode a role name to decide what it can show, only
#: ``user_has_permission``. See the master reference doc §10.3 for the
#: target role list this mirrors.
ROLE_PERMISSIONS = {
    Role.OWNER: ALL_PERMISSIONS,
    Role.ADMINISTRATOR: ALL_PERMISSIONS - _OWNER_ONLY,
    Role.CATALOG_MANAGER: frozenset({DASHBOARD_VIEW, REPORTS_VIEW}) | _CATALOG_READ_WRITE,
    Role.ORDER_MANAGER: frozenset({DASHBOARD_VIEW, REPORTS_VIEW}) | _ORDER_READ_WRITE,
    Role.CONTENT_EDITOR: frozenset({DASHBOARD_VIEW}) | _CONTENT_READ_WRITE,
    Role.ANALYST: frozenset({
        DASHBOARD_VIEW, REPORTS_VIEW, PRODUCT_VIEW, ORDER_VIEW, CUSTOMER_VIEW,
        COUPON_VIEW, RETURN_VIEW, REFUND_VIEW, AUDIT_LOG_VIEW,
    }),
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


def membership_has_permission(membership, permission):
    """Whether an already-looked-up ``membership`` (may be ``None``) grants
    ``permission``. Avoids a second query when a caller (the ``staff_required``
    decorator) already resolved the membership once for this request."""
    if membership is None:
        return False
    return permission in ROLE_PERMISSIONS.get(membership.role, frozenset())


def user_has_permission(user, store, permission):
    """Whether ``user``'s active membership in ``store`` grants ``permission``.

    ``permission`` must be one of the module-level constants above.
    """
    return membership_has_permission(get_active_membership(user, store), permission)
