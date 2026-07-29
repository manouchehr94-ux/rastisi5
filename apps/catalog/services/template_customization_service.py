"""تشخیص سفارشی‌سازیِ رکوردهای متعلق به Store — نگاه کنید به ADR-28.

چون ردیف‌های ``IndustryTemplate*`` پس از ساخت هرگز تغییر نمی‌کنند
(ADR-25)، خودِ رکورد مبدأ (``source_template_*``) همان لحظه‌ی نصب است —
نیازی به یک جدول عکس‌فوریِ جداگانه نیست. رکوردی که هیچ FK مبدأ ندارد
(چه چون مرچنت آن را از صفر ساخته، چه چون پیش از افزودن این FK نصب شده)
همیشه محافظه‌کارانه «سفارشی‌شده» فرض می‌شود."""


def is_category_customized(category) -> bool:
    source = category.source_template_category
    if source is None:
        return True
    if category.name != source.name or category.icon != source.icon:
        return True
    if not category.is_active:
        return True
    parent_source_pk = category.parent.source_template_category_id if category.parent_id else None
    if bool(category.parent_id) != bool(source.parent_id):
        return True
    if source.parent_id and parent_source_pk != source.parent_id:
        return True
    return False


def is_attribute_customized(attribute) -> bool:
    source = attribute.source_template_attribute
    if source is None:
        return True
    return (
        attribute.label != source.label
        or attribute.data_type != source.data_type
        or attribute.display_type != source.display_type
        or attribute.unit != source.unit
        or attribute.is_variant_axis != source.is_variant_axis
        or not attribute.is_active
    )


def is_value_customized(value) -> bool:
    source = value.source_template_value
    if source is None:
        return True
    return (
        value.label != source.label
        or value.color_hex != source.color_hex
        or not value.is_active
    )


def is_schema_entry_customized(entry) -> bool:
    source = entry.source_template_mapping
    if source is None:
        return True
    return (
        entry.group != source.group
        or entry.is_required != source.is_required
        or entry.is_filterable_override != source.is_filterable
        or entry.is_comparable_override != source.is_comparable
        or entry.is_searchable_override != source.is_searchable
        or entry.help_text != source.help_text
        or entry.placeholder != source.placeholder
        or not entry.is_visible_on_storefront
    )


def detect_installation_customizations(installation) -> dict:
    """مجموعه‌ی کدهای پایدارِ رکوردهای سفارشی‌شده‌ی این نصب — برای برنامه‌ریزیِ به‌روزرسانی امن."""
    from apps.catalog.models import Attribute, AttributeValue, Category, CategoryAttributeSchema

    store = installation.store

    customized_category_codes = {
        c.source_template_category.code
        for c in Category.objects.filter(store=store, source_template_category__isnull=False).select_related(
            "source_template_category", "parent__source_template_category",
        )
        if is_category_customized(c)
    }
    merchant_created_categories = list(
        Category.objects.filter(store=store, source_template_category__isnull=True)
    )

    customized_attribute_codes = {
        a.source_template_attribute.code
        for a in Attribute.objects.filter(store=store, source_template_attribute__isnull=False).select_related(
            "source_template_attribute",
        )
        if is_attribute_customized(a)
    }
    merchant_created_attributes = list(
        Attribute.objects.filter(store=store, source_template_attribute__isnull=True)
    )

    customized_value_keys = {
        f"{v.attribute.source_template_attribute.code}:{v.source_template_value.label}"
        for v in AttributeValue.objects.filter(
            attribute__store=store, source_template_value__isnull=False,
            attribute__source_template_attribute__isnull=False,
        ).select_related("source_template_value", "attribute__source_template_attribute")
        if is_value_customized(v)
    }

    customized_mapping_keys = {
        f"{e.category.source_template_category.code}:{e.attribute.source_template_attribute.code}"
        for e in CategoryAttributeSchema.objects.filter(
            category__store=store, source_template_mapping__isnull=False,
            category__source_template_category__isnull=False, attribute__source_template_attribute__isnull=False,
        ).select_related("source_template_mapping", "category__source_template_category",
                          "attribute__source_template_attribute")
        if is_schema_entry_customized(e)
    }

    return {
        "customized_category_codes": customized_category_codes,
        "merchant_created_categories": merchant_created_categories,
        "customized_attribute_codes": customized_attribute_codes,
        "merchant_created_attributes": merchant_created_attributes,
        "customized_value_keys": customized_value_keys,
        "customized_mapping_keys": customized_mapping_keys,
    }
