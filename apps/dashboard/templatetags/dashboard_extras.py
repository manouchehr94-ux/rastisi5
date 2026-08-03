from django import template

from apps.catalog.models import Product
from apps.dashboard.services.catalog_admin_service import category_chain as _category_chain
from apps.dashboard.services.catalog_admin_service import product_price_range as _product_price_range
from apps.dashboard.services.dashboard_service import ORDER_STATUS_BADGE, PAYMENT_STATUS_BADGE
from apps.dashboard.services.orders_admin_service import TRANSACTION_STATUS_BADGE
from apps.dashboard.services.sms_admin_service import LOG_STATUS_BADGE

register = template.Library()


@register.filter
def order_status_badge(status):
    return ORDER_STATUS_BADGE.get(status, "b-gray")


@register.filter
def sms_status_badge(status):
    return LOG_STATUS_BADGE.get(status, "b-gray")


@register.filter
def get_item(mapping, key):
    """جست‌وجویِ یک dict با کلیدی که خودش یک متغیرِ تمپلیت است — Django
    Template Language این کار را برایِ ``dict.key`` ثابت انجام می‌دهد اما
    نه برایِ کلیدِ پویا، پس یک فیلترِ عمومیِ کوچک لازم است."""
    if not mapping:
        return ""
    return mapping.get(key, "")


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
def price_range_min(product):
    return _product_price_range(product)[0]


@register.filter
def price_range_max(product):
    return _product_price_range(product)[1]


@register.filter
def is_price_range(product):
    low, high = _product_price_range(product)
    return low != high


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


@register.filter
def product_type_badge(product_type):
    return "b-purple" if product_type == Product.ProductType.VARIABLE else "b-blue"


@register.filter
def product_type_label(product_type):
    return dict(Product.ProductType.choices).get(product_type, product_type)
