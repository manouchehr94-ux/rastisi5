from django import template

from apps.dashboard.services.dashboard_service import ORDER_STATUS_BADGE, PAYMENT_STATUS_BADGE

register = template.Library()


@register.filter
def order_status_badge(status):
    return ORDER_STATUS_BADGE.get(status, "b-gray")


@register.filter
def payment_status_badge(status):
    return PAYMENT_STATUS_BADGE.get(status, "b-gray")
