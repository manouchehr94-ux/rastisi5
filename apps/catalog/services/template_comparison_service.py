"""مقایسه‌ی قطعیِ دو نسخه‌ی یک خانواده‌ی صنف — بر اساس کدِ پایدار، نه برچسب نمایشی.

نگاه کنید به بخش ۱۷ پرامپت فاز ۱F و ADR-29 (سیاست به‌روزرسانیِ امن)."""

from dataclasses import dataclass, field

from apps.catalog.models import (
    IndustryTemplateCategoryAttributeMapping,
    IndustryTemplateRecommendedOption,
)


class TemplateComparisonError(Exception):
    pass


@dataclass
class DiffEntry:
    kind: str  # category | attribute | value | mapping | recommendation
    change_type: str  # added | changed | removed
    code: str  # شناسه‌ی پایدار (مثلاً "category:clothing-mens" یا "mapping:clothing-mens:material")
    label: str
    details: dict = field(default_factory=dict)

    @property
    def change_id(self) -> str:
        return f"{self.kind}:{self.change_type}:{self.code}"


@dataclass
class TemplateDiff:
    old_template: object
    new_template: object
    added: list = field(default_factory=list)
    changed: list = field(default_factory=list)
    removed: list = field(default_factory=list)

    def all_entries(self) -> list:
        return [*self.added, *self.changed, *self.removed]

    def find(self, change_id: str):
        for entry in self.all_entries():
            if entry.change_id == change_id:
                return entry
        return None


def _category_identity(category):
    return {
        "name": category.name, "icon": category.icon,
        "parent_code": category.parent.code if category.parent_id else None,
    }


def _attribute_identity(attribute):
    return {
        "label": attribute.label, "data_type": attribute.data_type, "display_type": attribute.display_type,
        "unit": attribute.unit, "is_variant_axis": attribute.is_variant_axis,
    }


def _mapping_identity(mapping):
    return {
        "group": mapping.group, "display_order": mapping.display_order, "is_required": mapping.is_required,
        "is_filterable": mapping.is_filterable, "is_comparable": mapping.is_comparable,
        "is_searchable": mapping.is_searchable, "help_text": mapping.help_text, "placeholder": mapping.placeholder,
    }


def _diff_dict(old_by_code: dict, new_by_code: dict, kind: str, identity_fn, label_fn, out_diff: TemplateDiff):
    for code, new_item in sorted(new_by_code.items()):
        if code not in old_by_code:
            out_diff.added.append(DiffEntry(kind=kind, change_type="added", code=code, label=label_fn(new_item)))
            continue
        old_identity = identity_fn(old_by_code[code])
        new_identity = identity_fn(new_item)
        if old_identity != new_identity:
            changed_fields = {
                field_name: {"old": old_identity[field_name], "new": new_identity[field_name]}
                for field_name in new_identity
                if old_identity.get(field_name) != new_identity[field_name]
            }
            out_diff.changed.append(DiffEntry(
                kind=kind, change_type="changed", code=code, label=label_fn(new_item), details=changed_fields,
            ))
    for code, old_item in sorted(old_by_code.items()):
        if code not in new_by_code:
            out_diff.removed.append(DiffEntry(kind=kind, change_type="removed", code=code, label=label_fn(old_item)))


def compare_template_versions(old_template, new_template) -> TemplateDiff:
    """دیفِ ساختاریافته‌ی دو نسخه — با هویت مبتنی‌بر کد پایدار (نه برچسب)."""
    if old_template.slug != new_template.slug:
        raise TemplateComparisonError("فقط نسخه‌های یک خانواده‌ی صنف (اسلاگ یکسان) قابل‌مقایسه‌اند.")

    diff = TemplateDiff(old_template=old_template, new_template=new_template)

    old_categories = {c.code: c for c in old_template.categories.select_related("parent").all()}
    new_categories = {c.code: c for c in new_template.categories.select_related("parent").all()}
    _diff_dict(old_categories, new_categories, "category", _category_identity, lambda c: c.name, diff)

    old_attributes = {a.code: a for a in old_template.attributes.all()}
    new_attributes = {a.code: a for a in new_template.attributes.all()}
    _diff_dict(old_attributes, new_attributes, "attribute", _attribute_identity, lambda a: a.label, diff)

    for code, new_attr in sorted(new_attributes.items()):
        old_attr = old_attributes.get(code)
        old_values = {v.label.strip().lower(): v for v in (old_attr.values.all() if old_attr else [])}
        new_values = {v.label.strip().lower(): v for v in new_attr.values.all()}
        for key, value in sorted(new_values.items()):
            if key not in old_values:
                diff.added.append(DiffEntry(
                    kind="value", change_type="added", code=f"{code}:{value.label}", label=value.label,
                ))
        for key, value in sorted(old_values.items()):
            if key not in new_values:
                diff.removed.append(DiffEntry(
                    kind="value", change_type="removed", code=f"{code}:{value.label}", label=value.label,
                ))

    old_mappings = {
        f"{m.template_category.code}:{m.template_attribute.code}": m
        for m in IndustryTemplateCategoryAttributeMapping.objects.filter(
            template_category__industry_template=old_template,
        ).select_related("template_category", "template_attribute")
    }
    new_mappings = {
        f"{m.template_category.code}:{m.template_attribute.code}": m
        for m in IndustryTemplateCategoryAttributeMapping.objects.filter(
            template_category__industry_template=new_template,
        ).select_related("template_category", "template_attribute")
    }
    _diff_dict(
        old_mappings, new_mappings, "mapping", _mapping_identity,
        lambda m: f"{m.template_category.name} — {m.template_attribute.label}", diff,
    )

    old_recs = {
        f"{r.template_category.code}:{r.template_attribute.code}": r
        for r in IndustryTemplateRecommendedOption.objects.filter(
            template_category__industry_template=old_template,
        ).select_related("template_category", "template_attribute")
    }
    new_recs = {
        f"{r.template_category.code}:{r.template_attribute.code}": r
        for r in IndustryTemplateRecommendedOption.objects.filter(
            template_category__industry_template=new_template,
        ).select_related("template_category", "template_attribute")
    }
    for code, rec in sorted(new_recs.items()):
        if code not in old_recs:
            diff.added.append(DiffEntry(
                kind="recommendation", change_type="added", code=code,
                label=f"{rec.template_category.name} — {rec.template_attribute.label}",
            ))
    for code, rec in sorted(old_recs.items()):
        if code not in new_recs:
            diff.removed.append(DiffEntry(
                kind="recommendation", change_type="removed", code=code,
                label=f"{rec.template_category.name} — {rec.template_attribute.label}",
            ))

    return diff
