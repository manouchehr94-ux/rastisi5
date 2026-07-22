from django import template

from apps.dashboard.services.catalog_admin_service import category_chain as _category_chain
from apps.dashboard.services.dashboard_service import ORDER_STATUS_BADGE, PAYMENT_STATUS_BADGE
from apps.dashboard.services.orders_admin_service import TRANSACTION_STATUS_BADGE

register = template.Library()


@register.filter
def order_status_badge(status):
    return ORDER_STATUS_BADGE.get(status, "b-gray")


@register.filter
def transaction_status_badge(status):
    return TRANSACTION_STATUS_BADGE.get(status, "b-gray")


@register.filter
def payment_status_badge(status):
    return PAYMENT_STATUS_BADGE.get(status, "b-gray")


@register.filter
def category_chain(category):
    return _category_chain(category)


@register.filter
def product_status_badge(product):
    if product.stock == 0:
        return "b-red"
    if product.status == "inactive":
        return "b-gray"
    return "b-green"


@register.filter
def dict_get(mapping, key):
    return mapping.get(key, 0)


@register.filter
def product_status_label(product):
    if product.stock == 0:
        return "ناموجود"
    if product.status == "inactive":
        return "غیرفعال"
    return "فعال"
