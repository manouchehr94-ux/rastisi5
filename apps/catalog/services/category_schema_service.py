"""طرح ویژگیِ دسته‌بندی: نگاشت Attribute<->Category، حل وراثت، و سیاست
حفظِ مقدار ویژگی هنگام تغییر دسته‌بندی کالا.

ADR-23 (وراثت) و ADR-24 (چرخه‌ی عمر مقدار هنگام تغییر دسته‌بندی) در
``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`` را نگاه کنید.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import Category, CategoryAttributeSchema, Product, ProductAttributeValue


class CategorySchemaError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت طرح ویژگی دسته‌بندی."""


@dataclass
class ResolvedSchemaEntry:
    schema: CategoryAttributeSchema
    attribute: object
    group: str
    group_order: int
    display_order: int
    is_required: bool
    is_filterable: bool
    is_comparable: bool
    is_searchable: bool
    help_text: str
    placeholder: str
    is_visible_on_storefront: bool
    is_inherited: bool
    source_category: Category


def _ancestor_chain(category: Category) -> list[Category]:
    """دسته‌بندی و همه‌ی اجدادش را از نزدیک‌ترین به دورترین برمی‌گرداند."""
    chain = [category]
    current = category
    seen_ids = {category.pk}
    while current.parent_id:
        parent = current.parent
        if parent.pk in seen_ids:
            break  # جلوگیری از حلقه‌ی احتمالی داده‌ی خراب — هرگز نباید رخ دهد
        chain.append(parent)
        seen_ids.add(parent.pk)
        current = parent
    return chain


def resolve_category_schema(category: Category | None) -> list[ResolvedSchemaEntry]:
    """طرح نرمال‌شده‌ی ویژگی‌های یک دسته‌بندی را برمی‌گرداند — نزدیک‌ترین نگاشت برنده است.

    خروجی یک فهرست بدون تکرار (هر Attribute حداکثر یک‌بار)، مرتب‌شده طبق
    ``group_order``/``display_order``ِ نگاشت *برنده*. نگاه کنید به ADR-23.

    ``category=None`` یک فهرستِ خالی می‌دهد — نه خطا: پیش‌نویسِ داخلیِ در حالِ
    ساختِ کالا (``Product.is_draft_placeholder``) تا پیش از انتخابِ دسته‌بندی
    توسطِ merchant، ``category=None`` دارد (نگاه کنید به
    ``apps.catalog.services.product_draft_service``)."""
    if category is None:
        return []
    chain = _ancestor_chain(category)
    resolved: dict[int, ResolvedSchemaEntry] = {}

    for index, node in enumerate(chain):
        is_self = index == 0
        entries = (
            CategoryAttributeSchema.objects.filter(category=node)
            .select_related("attribute")
        )
        for entry in entries:
            if not is_self and not entry.is_inherited_by_children:
                continue
            if entry.attribute_id in resolved:
                continue  # نزدیک‌ترین (پیش‌تر پردازش‌شده) همیشه برنده است
            resolved[entry.attribute_id] = ResolvedSchemaEntry(
                schema=entry,
                attribute=entry.attribute,
                group=entry.group,
                group_order=entry.group_order,
                display_order=entry.display_order,
                is_required=entry.is_required,
                is_filterable=entry.is_filterable,
                is_comparable=entry.is_comparable,
                is_searchable=entry.is_searchable,
                help_text=entry.help_text,
                placeholder=entry.placeholder,
                is_visible_on_storefront=entry.is_visible_on_storefront,
                is_inherited=not is_self,
                source_category=node,
            )

    return sorted(resolved.values(), key=lambda e: (e.group_order, e.display_order, e.attribute.label))


@transaction.atomic
def add_category_attribute(category: Category, attribute, **fields) -> CategoryAttributeSchema:
    if attribute.store_id != category.store_id:
        raise CategorySchemaError("این ویژگی متعلق به فروشگاه دیگری است.")
    if CategoryAttributeSchema.objects.filter(category=category, attribute=attribute).exists():
        raise CategorySchemaError(f"ویژگی «{attribute.label}» قبلاً به این دسته‌بندی اضافه شده است.")

    fields.setdefault("display_order", CategoryAttributeSchema.objects.filter(category=category).count())
    entry = CategoryAttributeSchema(category=category, attribute=attribute, **fields)
    try:
        entry.full_clean()
    except ValidationError as exc:
        raise CategorySchemaError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    entry.save()
    return entry


@transaction.atomic
def update_category_attribute(entry: CategoryAttributeSchema, **fields) -> CategoryAttributeSchema:
    for key, value in fields.items():
        setattr(entry, key, value)
    try:
        entry.full_clean()
    except ValidationError as exc:
        raise CategorySchemaError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    entry.save()
    return entry


def remove_category_attribute(entry: CategoryAttributeSchema) -> None:
    entry.delete()


@transaction.atomic
def reorder_category_attributes(category: Category, ordered_ids: list[int]) -> None:
    entries = {e.pk: e for e in CategoryAttributeSchema.objects.filter(category=category, pk__in=ordered_ids)}
    valid_ids = [entry_id for entry_id in ordered_ids if entry_id in entries]
    updated = []
    for order, entry_id in enumerate(valid_ids):
        entry = entries[entry_id]
        entry.display_order = order
        updated.append(entry)
    if updated:
        CategoryAttributeSchema.objects.bulk_update(updated, ["display_order"])


def orphaned_product_attribute_values(product: Product):
    """مقادیر ویژگیِ کالا که در طرح ویژگیِ دسته‌بندیِ *فعلی* کالا وجود ندارند.

    هرگز چیزی حذف نمی‌کند — فقط QuerySet قابل‌نمایش/قابل‌پاک‌سازی برمی‌گرداند.
    نگاه کنید به ADR-24."""
    current_attribute_ids = {e.attribute.pk for e in resolve_category_schema(product.category)}
    return ProductAttributeValue.objects.filter(product=product).exclude(attribute_id__in=current_attribute_ids)


def cleanup_orphaned_attribute_values(product: Product) -> int:
    """مقادیر ویژگیِ منسوخ (خارج از طرح دسته‌بندیِ فعلی) را با تأیید صریح مدیر حذف می‌کند."""
    queryset = orphaned_product_attribute_values(product)
    count = queryset.count()
    queryset.delete()
    return count
