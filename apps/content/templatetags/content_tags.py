from django import template

from apps.content.services import resolve_destination_context

register = template.Library()


@register.simple_tag
def resolve_destination(instance):
    """حل مقصد یک شیء DestinationMixin و بازگرداندن context شامل url, open_new_tab, rel."""
    return resolve_destination_context(instance)
