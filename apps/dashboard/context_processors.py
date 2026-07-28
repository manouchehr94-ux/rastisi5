"""Permission-aware navigation flags for merchant-admin templates.

Reads ``request.store_membership`` — set once per request by
``apps.dashboard.decorators.staff_required`` — so this never issues its own
database query. Requests that never went through ``staff_required`` (every
non-dashboard page) get an empty dict back, which is intentional: templates
outside ``apps.dashboard`` never reference these variable names, and Django
silently renders an undefined template variable as empty/falsy, so there is
nothing to guard here.
"""

from apps.stores.authorization import (
    CATEGORY_MANAGE,
    CONTENT_MANAGE,
    CUSTOMER_VIEW,
    MEDIA_MANAGE,
    ORDER_VIEW,
    PRODUCT_VIEW,
    REPORTS_VIEW,
    SETTINGS_MANAGE,
    membership_has_permission,
)


def merchant_permissions(request):
    membership = getattr(request, "store_membership", None)
    if membership is None:
        return {}
    return {
        "can_view_products": membership_has_permission(membership, PRODUCT_VIEW),
        "can_manage_categories": membership_has_permission(membership, CATEGORY_MANAGE),
        "can_view_orders": membership_has_permission(membership, ORDER_VIEW),
        "can_view_customers": membership_has_permission(membership, CUSTOMER_VIEW),
        "can_view_reports": membership_has_permission(membership, REPORTS_VIEW),
        "can_manage_settings": membership_has_permission(membership, SETTINGS_MANAGE),
        "can_manage_content": membership_has_permission(membership, CONTENT_MANAGE),
        "can_manage_media": membership_has_permission(membership, MEDIA_MANAGE),
    }
