"""برنامه‌ریزی و اعمالِ امنِ به‌روزرسانیِ نصبِ قالب صنف — نگاه کنید به ADR-29.

فقط تغییرات «افزودنیِ امن» (safe_additive) در این فاز واقعاً اعمال
می‌شوند؛ تغییرات نیازمند بازبینی فقط نمایش داده می‌شوند و تغییرات مخرب یا
برخوردکننده با سفارشی‌سازیِ مرچنت همیشه مسدودند — هرگز به‌طور خودکار
اعمال نمی‌شوند."""

from dataclasses import dataclass, field

from django.db import transaction

from apps.catalog.models import (
    Attribute,
    AttributeValue,
    Category,
    CategoryAttributeSchema,
    CategoryRecommendedOption,
    StoreTemplateUpdate,
)
from apps.catalog.services.template_comparison_service import compare_template_versions
from apps.catalog.services.template_customization_service import detect_installation_customizations


class TemplateUpdateError(Exception):
    """خطای قابل‌نمایش هنگام برنامه‌ریزی یا اعمالِ به‌روزرسانیِ قالب صنف."""


@dataclass
class UpdateChange:
    diff_entry: object
    bucket: str  # safe_additive | review_required | blocked
    reason: str = ""

    @property
    def change_id(self) -> str:
        return self.diff_entry.change_id


@dataclass
class UpdatePlan:
    installation: object
    from_template: object
    target_template: object
    eligible: bool
    blocking_errors: list = field(default_factory=list)
    safe_additive: list = field(default_factory=list)
    review_required: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    customizations: dict = field(default_factory=dict)

    @property
    def default_selected_change_ids(self) -> list:
        return [c.change_id for c in self.safe_additive]

    def find_change(self, change_id: str):
        for change in (*self.safe_additive, *self.review_required, *self.blocked):
            if change.change_id == change_id:
                return change
        return None


def _customization_key(entry, customizations) -> bool:
    if entry.kind == "category":
        return entry.code in customizations.get("customized_category_codes", set())
    if entry.kind == "attribute":
        return entry.code in customizations.get("customized_attribute_codes", set())
    if entry.kind == "value":
        return entry.code in customizations.get("customized_value_keys", set())
    if entry.kind == "mapping":
        return entry.code in customizations.get("customized_mapping_keys", set())
    return False


def plan_template_update(installation, target_template) -> UpdatePlan:
    """برنامه‌ی به‌روزرسانی — واقعیت‌محور، هرگز چیزی این‌جا اعمال نمی‌شود."""
    from_template = installation.industry_template
    blocking_errors = []

    if target_template.slug != from_template.slug:
        blocking_errors.append("قالب مقصد باید از همان خانواده‌ی صنف باشد.")
    if target_template.pk == from_template.pk:
        blocking_errors.append("قالب مقصد نمی‌تواند همان نسخه‌ی فعلیِ نصب‌شده باشد.")
    elif target_template.version <= from_template.version:
        blocking_errors.append("نسخه‌ی مقصد باید جدیدتر از نسخه‌ی فعلیِ نصب‌شده باشد.")
    if not target_template.is_offerable_for_new_installation:
        blocking_errors.append(f"قالب مقصد در وضعیت «{target_template.readiness}» است و برای به‌روزرسانی در دسترس نیست.")

    if blocking_errors:
        return UpdatePlan(
            installation=installation, from_template=from_template, target_template=target_template,
            eligible=False, blocking_errors=blocking_errors,
        )

    diff = compare_template_versions(from_template, target_template)
    customizations = detect_installation_customizations(installation)
    store = installation.store

    safe_additive: list[UpdateChange] = []
    review_required: list[UpdateChange] = []
    blocked: list[UpdateChange] = []

    existing_attribute_by_code = {a.code: a for a in Attribute.objects.filter(store=store)}

    for entry in diff.added:
        if entry.kind == "attribute":
            target_attr = target_template.attributes.get(code=entry.code)
            existing = existing_attribute_by_code.get(entry.code)
            if existing is not None and existing.data_type != target_attr.data_type:
                blocked.append(UpdateChange(
                    diff_entry=entry, bucket="blocked",
                    reason=f"ویژگیِ «{entry.code}» در فروشگاه شما با نوعِ داده‌ای متفاوتی از قبل وجود دارد.",
                ))
                continue
        safe_additive.append(UpdateChange(diff_entry=entry, bucket="safe_additive"))

    for entry in diff.changed:
        if _customization_key(entry, customizations):
            blocked.append(UpdateChange(
                diff_entry=entry, bucket="blocked",
                reason="این رکورد توسط شما سفارشی شده است؛ هرگز به‌طور خودکار بازنویسی نمی‌شود.",
            ))
        else:
            review_required.append(UpdateChange(diff_entry=entry, bucket="review_required"))

    for entry in diff.removed:
        blocked.append(UpdateChange(
            diff_entry=entry, bucket="blocked",
            reason="حذف در به‌روزرسانیِ خودکار پشتیبانی نمی‌شود؛ رکورد فعلیِ شما حفظ می‌شود.",
        ))

    return UpdatePlan(
        installation=installation, from_template=from_template, target_template=target_template, eligible=True,
        safe_additive=safe_additive, review_required=review_required, blocked=blocked, customizations=customizations,
    )


def _apply_category_additions(store, target_template, entries, category_map: dict):
    """ساخت لایه‌به‌لایه‌ی دسته‌بندی‌های جدید — والد همیشه قبل از فرزند (مثل نصب اولیه)."""
    pending = {e.diff_entry.code: target_template.categories.get(code=e.diff_entry.code) for e in entries}
    applied = []
    while pending:
        progressed = []
        for code, template_category in list(pending.items()):
            parent_pk = template_category.parent_id
            if parent_pk and parent_pk not in category_map:
                continue
            parent = category_map.get(parent_pk) if parent_pk else None
            category = Category(
                store=store, name=template_category.name, icon=template_category.icon, parent=parent,
                order=template_category.display_order, source_template_category=template_category,
                slug=_unique_category_slug(store, template_category.name),
            )
            category.full_clean(exclude=["slug"])
            category.save()
            category_map[template_category.pk] = category
            applied.append(code)
            progressed.append(code)
        if not progressed:
            raise TemplateUpdateError("ساختار دسته‌بندی‌های جدید نامعتبر است (زنجیره‌ی والد ناقص).")
        for code in progressed:
            pending.pop(code)
    return applied


def _unique_category_slug(store, name: str) -> str:
    from django.utils.text import slugify

    base = slugify(name, allow_unicode=True).strip("-") or "category"
    candidate = base
    counter = 2
    while Category.objects.filter(store=store, slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def apply_template_update(installation, target_template, selected_change_ids, actor) -> StoreTemplateUpdate:
    """اعمالِ اتمیکِ تغییرات افزودنیِ انتخاب‌شده — نگاه کنید به ADR-29.

    فقط ورودی‌هایی که واقعاً در ``safe_additive``ِ برنامه‌ی تازه‌محاسبه‌شده
    هستند اعمال می‌شوند؛ برنامه‌ی قدیمیِ ارسالی از کلاینت هرگز معتبر فرض
    نمی‌شود — همیشه این تابع خودش دوباره محاسبه می‌کند."""
    idempotency_key = f"{installation.pk}:{target_template.pk}"
    already_completed = StoreTemplateUpdate.objects.filter(
        idempotency_key=idempotency_key, status=StoreTemplateUpdate.Status.COMPLETED,
    ).exists()
    if already_completed:
        raise TemplateUpdateError("این به‌روزرسانی قبلاً با موفقیت اعمال شده است.")

    plan = plan_template_update(installation, target_template)
    if not plan.eligible:
        raise TemplateUpdateError("؛ ".join(plan.blocking_errors))

    safe_ids = {c.change_id for c in plan.safe_additive}
    selected_set = set(selected_change_ids)
    invalid_selection = selected_set - safe_ids
    if invalid_selection:
        raise TemplateUpdateError(
            "این تغییرات قابل‌انتخاب/اعمال نیستند (نیازمند بازبینی یا مسدودند): "
            + "، ".join(sorted(invalid_selection))
        )

    update_record, _created = StoreTemplateUpdate.objects.update_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "store": installation.store, "installation": installation, "from_template": plan.from_template,
            "target_template": target_template, "actor": actor, "status": StoreTemplateUpdate.Status.PENDING,
            "selected_change_ids": sorted(selected_set), "applied_changes": [], "skipped_changes": [],
            "conflicts": [c.change_id for c in plan.blocked], "failure_reason": "",
        },
    )

    try:
        with transaction.atomic():
            store = installation.store
            selected_entries = [c for c in plan.safe_additive if c.change_id in selected_set]
            skipped_entries = [c for c in plan.safe_additive if c.change_id not in selected_set]

            category_source_map = {
                c.source_template_category_id: c
                for c in Category.objects.filter(store=store, source_template_category__isnull=False)
            }
            attribute_source_map = {a.code: a for a in Attribute.objects.filter(store=store)}

            applied_ids = []

            category_entries = [c for c in selected_entries if c.diff_entry.kind == "category"]
            if category_entries:
                applied_ids += [
                    f"category:added:{code}"
                    for code in _apply_category_additions(
                        store, target_template, category_entries, category_source_map,
                    )
                ]

            attribute_entries = [c for c in selected_entries if c.diff_entry.kind == "attribute"]
            for change in attribute_entries:
                template_attr = target_template.attributes.get(code=change.diff_entry.code)
                attribute, _created = Attribute.objects.get_or_create(
                    store=store, code=template_attr.code,
                    defaults={
                        "label": template_attr.label, "data_type": template_attr.data_type,
                        "display_type": template_attr.display_type, "unit": template_attr.unit,
                        "is_variant_axis": template_attr.is_variant_axis,
                        "display_order": template_attr.display_order,
                        "source_template_attribute": template_attr,
                    },
                )
                attribute_source_map[attribute.code] = attribute
                applied_ids.append(change.change_id)

            value_entries = [c for c in selected_entries if c.diff_entry.kind == "value"]
            for change in value_entries:
                attribute_code, _sep, value_label = change.diff_entry.code.partition(":")
                attribute = attribute_source_map.get(attribute_code)
                if attribute is None:
                    continue
                template_attr = target_template.attributes.get(code=attribute_code)
                template_value = template_attr.values.get(label=value_label)
                from apps.core.utils import normalization_key

                AttributeValue.objects.get_or_create(
                    attribute=attribute, normalized_label=normalization_key(template_value.label),
                    defaults={
                        "label": template_value.label, "value": template_value.value or template_value.label,
                        "color_hex": template_value.color_hex, "display_order": template_value.display_order,
                        "source_template_value": template_value,
                    },
                )
                applied_ids.append(change.change_id)

            mapping_entries = [c for c in selected_entries if c.diff_entry.kind == "mapping"]
            for change in mapping_entries:
                category_code, _sep, attribute_code = change.diff_entry.code.partition(":")
                template_category = target_template.categories.get(code=category_code)
                category = category_source_map.get(template_category.pk)
                attribute = attribute_source_map.get(attribute_code)
                if category is None or attribute is None:
                    continue
                from apps.catalog.models import IndustryTemplateCategoryAttributeMapping

                tcam = IndustryTemplateCategoryAttributeMapping.objects.get(
                    template_category=template_category, template_attribute__code=attribute_code,
                )
                CategoryAttributeSchema.objects.get_or_create(
                    category=category, attribute=attribute,
                    defaults={
                        "group": tcam.group, "group_order": tcam.group_order, "display_order": tcam.display_order,
                        "is_required": tcam.is_required, "is_filterable_override": tcam.is_filterable,
                        "is_comparable_override": tcam.is_comparable, "is_searchable_override": tcam.is_searchable,
                        "help_text": tcam.help_text, "placeholder": tcam.placeholder,
                        "source_template_mapping": tcam,
                    },
                )
                applied_ids.append(change.change_id)

            recommendation_entries = [c for c in selected_entries if c.diff_entry.kind == "recommendation"]
            for change in recommendation_entries:
                category_code, _sep, attribute_code = change.diff_entry.code.partition(":")
                template_category = target_template.categories.get(code=category_code)
                category = category_source_map.get(template_category.pk)
                attribute = attribute_source_map.get(attribute_code)
                if category is None or attribute is None:
                    continue
                from apps.catalog.models import IndustryTemplateRecommendedOption

                tro = IndustryTemplateRecommendedOption.objects.get(
                    template_category=template_category, template_attribute__code=attribute_code,
                )
                CategoryRecommendedOption.objects.get_or_create(
                    category=category, attribute=attribute, defaults={"display_order": tro.display_order},
                )
                applied_ids.append(change.change_id)

            installation.industry_template = target_template
            installation.installed_version = target_template.version
            installation.save(update_fields=["industry_template", "installed_version"])

            from django.utils import timezone

            update_record.status = StoreTemplateUpdate.Status.COMPLETED
            update_record.applied_changes = applied_ids
            update_record.skipped_changes = [c.change_id for c in skipped_entries]
            update_record.completed_at = timezone.now()
            update_record.save(update_fields=["status", "applied_changes", "skipped_changes", "completed_at"])
    except Exception as exc:
        update_record.status = StoreTemplateUpdate.Status.FAILED
        update_record.failure_reason = str(exc)
        update_record.save(update_fields=["status", "failure_reason"])
        raise

    return update_record
