"""پیش‌نمایش پیش از نصب و برنامه‌ی اثرِ نصب — نگاه کنید به بخش‌های ۱۳/۱۴ پرامپت فاز ۱F.

منطق برنامه‌ریزیِ این ماژول باید همان چیزی باشد که واقعاً در
``industry_template_service.install_industry_template`` اجرا می‌شود — تا
پیش‌نمایش هرگز نتیجه‌ای گمراه‌کننده ندهد (نگاه کنید به بخش ۱۴ پرامپت)."""

from dataclasses import dataclass, field

from apps.catalog.models import (
    Attribute,
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)
from apps.catalog.services.industry_template_service import can_install_industry_template
from apps.catalog.services.template_validation_service import validate_industry_template


@dataclass
class InstallationPlan:
    eligible: bool
    will_create_categories: int = 0
    will_create_attributes: int = 0
    will_create_values: int = 0
    will_create_mappings: int = 0
    will_create_recommendations: int = 0
    will_reuse_attributes: list = field(default_factory=list)
    blocking_errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def build_template_preview(template) -> dict:
    """داده‌ی کامل پیش‌نمایشِ مرچنت‌محور برای یک قالب صنف — پیش از هرگونه نصب."""
    categories = list(template.categories.select_related("parent").order_by("display_order", "code"))
    attributes = list(template.attributes.prefetch_related("values").order_by("display_order", "code"))
    mappings = list(
        IndustryTemplateCategoryAttributeMapping.objects.filter(template_category__industry_template=template)
        .select_related("template_category", "template_attribute").order_by("group_order", "display_order")
    )
    recommendations = list(
        IndustryTemplateRecommendedOption.objects.filter(template_category__industry_template=template)
        .select_related("template_category", "template_attribute").order_by("display_order")
    )

    children_by_parent: dict = {}
    for category in categories:
        children_by_parent.setdefault(category.parent_id, []).append(category)

    def build_node(category):
        return {
            "code": category.code, "name": category.name, "icon": category.icon,
            "children": [build_node(c) for c in children_by_parent.get(category.pk, [])],
        }

    hierarchy = [build_node(c) for c in children_by_parent.get(None, [])]

    mappings_by_category: dict = {}
    for mapping in mappings:
        mappings_by_category.setdefault(mapping.template_category.code, []).append({
            "attribute_code": mapping.template_attribute.code,
            "attribute_label": mapping.template_attribute.label,
            "group": mapping.group,
            "is_required": mapping.is_required,
            "is_filterable": mapping.is_filterable,
            "is_comparable": mapping.is_comparable,
            "is_searchable": mapping.is_searchable,
        })

    recommendations_by_category: dict = {}
    for rec in recommendations:
        recommendations_by_category.setdefault(rec.template_category.code, []).append({
            "attribute_code": rec.template_attribute.code, "attribute_label": rec.template_attribute.label,
        })

    value_count = sum(a.values.count() for a in attributes)
    validation = validate_industry_template(template)

    return {
        "template": template,
        "readiness": template.readiness,
        "counts": {
            "categories": len(categories), "attributes": len(attributes), "values": value_count,
            "mappings": len(mappings), "recommendations": len(recommendations),
        },
        "hierarchy": hierarchy,
        "attributes_by_category": mappings_by_category,
        "recommendations_by_category": recommendations_by_category,
        "required_attribute_codes": {m.template_attribute.code for m in mappings if m.is_required},
        "filterable_attribute_codes": {m.template_attribute.code for m in mappings if m.is_filterable},
        "comparable_attribute_codes": {m.template_attribute.code for m in mappings if m.is_comparable},
        "searchable_attribute_codes": {m.template_attribute.code for m in mappings if m.is_searchable},
        "validation": validation,
        "limitations": [
            "این قالب پس از نصب فقط یک‌بار روی هر فروشگاه قابل‌نصب است.",
            "پس از نصب، رکوردهای ساخته‌شده کاملاً متعلق به فروشگاه شما می‌شوند و سفارشی‌سازی آن‌ها هرگز توسط "
            "نسخه‌های بعدیِ قالب به‌طور خودکار بازنویسی نمی‌شود.",
        ],
        "installation_policy": "نصب فقط یک‌بار در طول عمر فروشگاه ممکن است (نگاه کنید به سیاست نسخه‌بندی قالب).",
        "customization_policy": "پس از نصب می‌توانید هر دسته‌بندی/ویژگی را مانند رکوردهای دستی ویرایش کنید؛ "
        "به‌روزرسانی‌های بعدیِ قالب هرگز رکورد سفارشی‌شده را بازنویسی نمی‌کنند.",
    }


def plan_industry_template_installation(store, template) -> InstallationPlan:
    """برنامه‌ی واقعیِ اثرِ نصب — مشتق از وضعیت فعلیِ Store، نه اعداد ثابت."""
    blocking_errors: list = []
    warnings: list = []

    try:
        can_install_industry_template(store)
    except Exception as exc:  # noqa: BLE001 — پیام قابل‌نمایش سرویس نصب
        blocking_errors.append(str(exc))

    if not template.is_offerable_for_new_installation:
        blocking_errors.append(f"قالب «{template.name}» برای نصب جدید در دسترس نیست (آمادگی: {template.readiness}).")

    categories = list(template.categories.all())
    attributes = list(template.attributes.all())
    mappings_count = IndustryTemplateCategoryAttributeMapping.objects.filter(
        template_category__industry_template=template,
    ).count()
    recommendations_count = IndustryTemplateRecommendedOption.objects.filter(
        template_category__industry_template=template,
    ).count()
    values_count = sum(a.values.count() for a in attributes)

    existing_codes = set(
        Attribute.objects.filter(store=store, code__in=[a.code for a in attributes]).values_list("code", flat=True)
    )
    will_reuse = sorted(existing_codes)
    will_create_attributes = len(attributes) - len(will_reuse)

    if not blocking_errors:
        validation = validate_industry_template(template)
        if not validation.is_valid:
            blocking_errors.append("قالب اعتبارسنجی ساختاری را رد می‌کند؛ نصب مسدود است.")

    return InstallationPlan(
        eligible=not blocking_errors,
        will_create_categories=len(categories),
        will_create_attributes=max(will_create_attributes, 0),
        will_create_values=values_count,
        will_create_mappings=mappings_count,
        will_create_recommendations=recommendations_count,
        will_reuse_attributes=will_reuse,
        blocking_errors=blocking_errors,
        warnings=warnings,
    )
