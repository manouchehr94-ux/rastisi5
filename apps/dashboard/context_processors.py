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
    ATTRIBUTE_MANAGE,
    AUDIT_LOG_VIEW,
    CATEGORY_MANAGE,
    CONTENT_MANAGE,
    COUPON_VIEW,
    CUSTOMER_VIEW,
    DISCOUNT_MANAGE,
    INVENTORY_MANAGE,
    MEDIA_MANAGE,
    ORDER_VIEW,
    PRODUCT_VIEW,
    REFUND_VIEW,
    REPORTS_VIEW,
    RESERVATION_VIEW,
    RETURN_VIEW,
    SETTINGS_MANAGE,
    SHIPPING_SETTINGS_VIEW,
    STAFF_MANAGE,
    TAX_SETTINGS_VIEW,
    TRANSFER_VIEW,
    WAREHOUSE_VIEW,
    membership_has_permission,
)


def merchant_permissions(request):
    membership = getattr(request, "store_membership", None)
    if membership is None:
        return {}
    return {
        "can_view_products": membership_has_permission(membership, PRODUCT_VIEW),
        "can_manage_categories": membership_has_permission(membership, CATEGORY_MANAGE),
        "can_manage_attributes": membership_has_permission(membership, ATTRIBUTE_MANAGE),
        "can_view_orders": membership_has_permission(membership, ORDER_VIEW),
        "can_view_customers": membership_has_permission(membership, CUSTOMER_VIEW),
        "can_view_reports": membership_has_permission(membership, REPORTS_VIEW),
        "can_manage_settings": membership_has_permission(membership, SETTINGS_MANAGE),
        "can_manage_content": membership_has_permission(membership, CONTENT_MANAGE),
        "can_manage_media": membership_has_permission(membership, MEDIA_MANAGE),
        "can_manage_staff": membership_has_permission(membership, STAFF_MANAGE),
        "can_manage_inventory": membership_has_permission(membership, INVENTORY_MANAGE),
        "can_view_coupons": (
            membership_has_permission(membership, COUPON_VIEW)
            or membership_has_permission(membership, DISCOUNT_MANAGE)
        ),
        "can_view_returns": membership_has_permission(membership, RETURN_VIEW),
        "can_view_refunds": membership_has_permission(membership, REFUND_VIEW),
        "can_view_audit_log": membership_has_permission(membership, AUDIT_LOG_VIEW),
        "can_view_warehouses": membership_has_permission(membership, WAREHOUSE_VIEW),
        "can_view_transfers": membership_has_permission(membership, TRANSFER_VIEW),
        "can_view_reservations": membership_has_permission(membership, RESERVATION_VIEW),
        "can_view_shipping_settings": membership_has_permission(membership, SHIPPING_SETTINGS_VIEW),
        "can_view_tax_settings": membership_has_permission(membership, TAX_SETTINGS_VIEW),
    }
