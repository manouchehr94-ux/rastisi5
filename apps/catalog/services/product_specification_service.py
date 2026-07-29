"""بازنمایی نرمال‌شده و گروه‌بندی‌شده‌ی مشخصات کالا — برای Merchant Admin و
مصرف آینده‌ی Storefront (هیچ فیلد اختصاصی کالا در قالب هاردکد نمی‌شود).

خروجی این ماژول تنها منبع حقیقت برای «مشخصات کالا» و «داده‌ی مقایسه» است؛
هیچ view/template نباید مستقیماً ProductAttributeValue را برای نمایش
پیمایش کند.
"""

from apps.catalog.models import Attribute, Product, ProductAttributeValue
from apps.catalog.services.category_schema_service import resolve_category_schema


def format_attribute_value(attribute, assignments: list) -> str:
    """مقدار(های) یک ویژگی را طبق نوع داده به رشته‌ی نمایشی تبدیل می‌کند؛ بدون مقدار یعنی رشته‌ی خالی."""
    if not assignments:
        return ""

    data_type = attribute.data_type
    if data_type == Attribute.DataType.MULTISELECT:
        labels = [a.value.label for a in assignments if a.value_id]
        return "، ".join(labels)
    if data_type in (Attribute.DataType.SELECT, Attribute.DataType.COLOR):
        assignment = assignments[0]
        return assignment.value.label if assignment.value_id else ""
    if data_type == Attribute.DataType.BOOLEAN:
        assignment = assignments[0]
        if assignment.boolean_value is None:
            return ""
        return "بله" if assignment.boolean_value else "خیر"
    if data_type == Attribute.DataType.NUMBER:
        assignment = assignments[0]
        if assignment.number_value is None:
            return ""
        number = assignment.number_value
        if number == number.to_integral_value():
            number_text = str(int(number))
        else:
            number_text = str(number)
        return f"{number_text} {attribute.unit}".strip()
    # TEXT / DATE
    return (assignments[0].text_value or "").strip()


def build_product_specification(product: Product, *, comparable_only: bool = False) -> list[dict]:
    """مشخصات کالا را طبق طرح ویژگیِ دسته‌بندیِ فعلی، گروه‌بندی‌شده و مرتب برمی‌گرداند.

    مقادیر خالی حذف می‌شوند (empty-value omission). ``comparable_only=True``
    فقط ویژگی‌های قابل‌مقایسه را برمی‌گرداند — برای داده‌ی مقایسه‌ی کالا."""
    schema_entries = resolve_category_schema(product.category)
    if comparable_only:
        schema_entries = [e for e in schema_entries if e.is_comparable]

    assignments_by_attribute: dict[int, list] = {}
    for assignment in ProductAttributeValue.objects.filter(product=product).select_related("attribute", "value"):
        assignments_by_attribute.setdefault(assignment.attribute_id, []).append(assignment)

    groups: dict[str, dict] = {}
    group_order_by_name: dict[str, int] = {}

    for entry in schema_entries:
        assignments = assignments_by_attribute.get(entry.attribute.pk, [])
        value_text = format_attribute_value(entry.attribute, assignments)
        if not value_text:
            continue  # حذف مقدار خالی

        group_name = entry.group or "سایر"
        if group_name not in groups:
            groups[group_name] = {"group": group_name, "group_order": entry.group_order, "attributes": []}
            group_order_by_name[group_name] = entry.group_order
        groups[group_name]["attributes"].append({
            "label": entry.attribute.label,
            "value": value_text,
            "unit": entry.attribute.unit,
            "is_comparable": entry.is_comparable,
            "is_required": entry.is_required,
        })

    return sorted(groups.values(), key=lambda g: g["group_order"])
