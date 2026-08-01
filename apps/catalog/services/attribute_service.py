"""لایه‌ی سرویس ویژگی‌ها (Attribute/AttributeValue) و انتساب توصیفی آن‌ها به کالا.

هیچ اعتبارسنجی یا محاسبه‌ی مهمی نباید در view یا template تکرار شود؛ همه از
همین توابع عبور می‌کنند. جدایی مفهومی «ویژگی توصیفی» از «محور تنوع‌سازِ
Product Option» عمداً است — نگاه کنید به ADR-19 در
``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md``. تولید/تطبیق
تنوع خودش در ``apps.catalog.services.variant_engine_service`` است.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Attribute, AttributeValue, Product, ProductAttributeValue, ProductOption
from apps.core.utils import normalize_text


class AttributeError_(Exception):
    """خطای قابل‌نمایش هنگام مدیریت ویژگی — نامش برای پرهیز از سایه‌انداختن روی builtins.AttributeError است."""


class AttributeInUseError(AttributeError_):
    """تلاش برای حذف قطعی ویژگی/مقداری که هنوز روی کالایی استفاده می‌شود."""


def _unique_code(store, label: str, *, exclude_pk=None) -> str:
    base = slugify(label, allow_unicode=True).strip("-") or "attr"
    candidate = base
    counter = 2
    qs = Attribute.objects.filter(store=store)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(code=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


@transaction.atomic
def create_attribute(store, *, label, code="", description="", data_type=Attribute.DataType.TEXT, display_type="",
                      unit="", is_required=False, is_filterable=False, is_searchable=False,
                      is_comparable=False, is_variant_axis=False, category=None) -> Attribute:
    label = normalize_text(label)
    if not label:
        raise AttributeError_("عنوان ویژگی نمی‌تواند خالی باشد.")
    code = normalize_text(code) or _unique_code(store, label)
    attribute = Attribute(
        store=store, label=label, code=code, description=description, data_type=data_type,
        display_type=display_type, unit=unit, is_required=is_required, is_filterable=is_filterable,
        is_searchable=is_searchable, is_comparable=is_comparable, is_variant_axis=is_variant_axis,
        category=category, display_order=Attribute.objects.filter(store=store).count(),
    )
    try:
        attribute.full_clean()
    except ValidationError as exc:
        raise AttributeError_("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    attribute.save()
    return attribute


@transaction.atomic
def update_attribute(attribute: Attribute, **fields) -> Attribute:
    for key, value in fields.items():
        setattr(attribute, key, value)
    try:
        attribute.full_clean()
    except ValidationError as exc:
        raise AttributeError_("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    attribute.save()
    return attribute


def archive_attribute(attribute: Attribute) -> Attribute:
    """ویژگی را غیرفعال می‌کند (نه حذف) — همیشه امن، حتی اگر روی کالایی استفاده شده باشد."""
    if attribute.is_active:
        attribute.is_active = False
        attribute.save(update_fields=["is_active", "updated_at"])
    return attribute


def activate_attribute(attribute: Attribute) -> Attribute:
    if not attribute.is_active:
        attribute.is_active = True
        attribute.save(update_fields=["is_active", "updated_at"])
    return attribute


def can_delete_attribute(attribute: Attribute) -> None:
    """اگر ویژگی روی کالایی (توصیفی یا محور تنوع) استفاده شده باشد، خطای قابل‌نمایش می‌دهد."""
    if ProductAttributeValue.objects.filter(attribute=attribute).exists():
        raise AttributeInUseError(
            f"ویژگی «{attribute.label}» روی حداقل یک کالا استفاده شده و قابل حذف نیست؛ آن را غیرفعال کنید."
        )
    if ProductOption.objects.filter(attribute=attribute).exists():
        raise AttributeInUseError(
            f"ویژگی «{attribute.label}» به‌عنوان محور تنوع حداقل یک کالا استفاده شده و قابل حذف نیست؛ "
            "آن را غیرفعال کنید."
        )


@transaction.atomic
def delete_attribute(attribute: Attribute) -> None:
    can_delete_attribute(attribute)
    attribute.delete()


@transaction.atomic
def create_attribute_value(attribute: Attribute, *, label, value="", color_hex="", swatch_image=None) -> AttributeValue:
    attribute_value = AttributeValue(
        attribute=attribute, label=label, value=value, color_hex=color_hex,
        display_order=attribute.values.count(),
    )
    if swatch_image is not None:
        attribute_value.swatch_image = swatch_image
    try:
        attribute_value.full_clean()
    except ValidationError as exc:
        raise AttributeError_("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    attribute_value.save()
    return attribute_value


@transaction.atomic
def update_attribute_value(attribute_value: AttributeValue, **fields) -> AttributeValue:
    for key, val in fields.items():
        setattr(attribute_value, key, val)
    try:
        attribute_value.full_clean()
    except ValidationError as exc:
        raise AttributeError_("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    attribute_value.save()
    return attribute_value


def can_delete_attribute_value(attribute_value: AttributeValue) -> None:
    if attribute_value.product_assignments.exists():
        raise AttributeInUseError(
            f"مقدار «{attribute_value.label}» روی حداقل یک کالا استفاده شده و قابل حذف نیست؛ آن را غیرفعال کنید."
        )
    if attribute_value.option_values.exists():
        raise AttributeInUseError(
            f"مقدار «{attribute_value.label}» در محور تنوع حداقل یک کالا استفاده شده و قابل حذف نیست؛ "
            "آن را غیرفعال کنید."
        )


@transaction.atomic
def delete_attribute_value(attribute_value: AttributeValue) -> None:
    can_delete_attribute_value(attribute_value)
    attribute_value.delete()


def archive_attribute_value(attribute_value: AttributeValue) -> AttributeValue:
    if attribute_value.is_active:
        attribute_value.is_active = False
        attribute_value.save(update_fields=["is_active", "updated_at"])
    return attribute_value


@transaction.atomic
def reorder_attribute_values(attribute: Attribute, ordered_ids: list[int]) -> None:
    values = {v.pk: v for v in attribute.values.filter(pk__in=ordered_ids)}
    valid_ids = [value_id for value_id in ordered_ids if value_id in values]
    updated = []
    for order, value_id in enumerate(valid_ids):
        value = values[value_id]
        value.display_order = order
        updated.append(value)
    if updated:
        AttributeValue.objects.bulk_update(updated, ["display_order"])


# --------------------------------------------------------------------------
# انتساب توصیفی ویژگی به کالا (ProductAttributeValue)
# --------------------------------------------------------------------------

_MULTISELECT_TYPES = frozenset({Attribute.DataType.MULTISELECT})


def _validate_typed_value(attribute: Attribute, *, value, text_value, number_value, boolean_value) -> None:
    data_type = attribute.data_type
    if data_type in Attribute.CHOICE_DATA_TYPES:
        if value is None:
            raise AttributeError_(f"برای ویژگی «{attribute.label}» باید یک مقدار انتخاب شود.")
        if value.attribute_id != attribute.pk:
            raise AttributeError_("این مقدار متعلق به ویژگی دیگری است.")
    elif data_type == Attribute.DataType.NUMBER:
        if number_value is None:
            raise AttributeError_(f"برای ویژگی «{attribute.label}» باید مقدار عددی وارد شود.")
    elif data_type == Attribute.DataType.BOOLEAN:
        if boolean_value is None:
            raise AttributeError_(f"برای ویژگی «{attribute.label}» باید مقدار بله/خیر مشخص شود.")
    else:  # TEXT / DATE
        if not (text_value or "").strip():
            raise AttributeError_(f"برای ویژگی «{attribute.label}» باید مقدار متنی وارد شود.")


@transaction.atomic
def set_product_attribute_value(product: Product, attribute: Attribute, *, value=None, text_value="",
                                 number_value=None, boolean_value=None) -> ProductAttributeValue:
    """انتساب تک‌مقداری (غیر چندانتخابی) را ایجاد یا جایگزین می‌کند.

    برای MULTISELECT از ``add_product_attribute_multiselect_value`` استفاده کنید — این
    تابع فقط یک ProductAttributeValue در هر (product, attribute) نگه می‌دارد."""
    if attribute.store_id != product.store_id:
        raise AttributeError_("این ویژگی متعلق به فروشگاه دیگری است.")
    if attribute.data_type in _MULTISELECT_TYPES:
        raise AttributeError_("برای ویژگی چندانتخابی از تابع افزودن مقدار استفاده کنید.")

    _validate_typed_value(
        attribute, value=value, text_value=text_value, number_value=number_value, boolean_value=boolean_value,
    )

    ProductAttributeValue.objects.filter(product=product, attribute=attribute).delete()
    assignment = ProductAttributeValue(
        product=product, attribute=attribute, value=value,
        text_value=text_value if attribute.data_type == Attribute.DataType.TEXT else "",
        number_value=number_value if attribute.data_type == Attribute.DataType.NUMBER else None,
        boolean_value=boolean_value if attribute.data_type == Attribute.DataType.BOOLEAN else None,
    )
    try:
        assignment.full_clean()
    except ValidationError as exc:
        raise AttributeError_("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    assignment.save()
    return assignment


@transaction.atomic
def add_product_attribute_multiselect_value(product: Product, attribute: Attribute, value) -> ProductAttributeValue:
    if attribute.store_id != product.store_id:
        raise AttributeError_("این ویژگی متعلق به فروشگاه دیگری است.")
    if attribute.data_type not in _MULTISELECT_TYPES:
        raise AttributeError_("این ویژگی چندانتخابی نیست.")
    if value.attribute_id != attribute.pk:
        raise AttributeError_("این مقدار متعلق به ویژگی دیگری است.")

    assignment, _created = ProductAttributeValue.objects.get_or_create(
        product=product, attribute=attribute, value=value,
    )
    return assignment


def remove_product_attribute_value(product: Product, attribute: Attribute, value=None) -> None:
    """انتساب توصیفی را حذف می‌کند — برای MULTISELECT یک مقدار مشخص، برای بقیه‌ی انواع کل انتساب."""
    qs = ProductAttributeValue.objects.filter(product=product, attribute=attribute)
    if value is not None:
        qs = qs.filter(value=value)
    qs.delete()
