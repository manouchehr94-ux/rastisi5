"""موتور تولید/تطبیق تنوع چندمحوره (Attribute/Option/Variant Engine) — Phase 1D.

طراحی کامل و توجیه هر تصمیم در سه ADR مستند است
(``docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md``):

* ADR-19 — جدایی ویژگی توصیفی از محور تنوع‌سازِ ``ProductOption``.
* ADR-20 — هویت پایدار ترکیب: ``VariantOptionValue`` + ``combination_key``
  مشتق‌شده، نه رشته‌ی نمایشی ``attribute``/``value``.
* ADR-21 — سیاست تطبیق: هرگز حذف قطعی نمی‌کند؛ ترکیب‌های منسوخ فقط
  ``is_obsolete=True`` می‌شوند و حذف یک محور نیازمند بازتولید صریح است.

این سرویس تنها مسیر ایجاد/تطبیق تنوع‌های چندمحوره است — Viewها باید نازک
بمانند و مستقیماً حاصل‌ضرب دکارتی محاسبه نکنند.

توجه: یک کالا نمی‌تواند هم‌زمان از مسیر قدیمی تک‌محوره
(``apps.catalog.services.variant_service``) و این موتور استفاده کند —
``add_product_option`` تا وقتی حداقل یک تنوع قدیمی (``combination_key=""``)
روی کالا وجود دارد، از ایجاد اولین محور جلوگیری می‌کند (نگاه کنید به
ADR-20، «Consequences»).
"""

import itertools
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import (
    Product,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    VariantOptionValue,
)
from apps.catalog.services.variant_service import generate_variant_sku
from apps.core.utils import normalize_text

#: حداکثر تعداد محور تنوع مجاز روی یک کالا. کنترل انفجار ترکیبی: با مقادیر
#: معمول (۳ تا ۶ مقدار در هر محور) عددی مثل ۴ محور می‌تواند به هزاران ترکیب
#: برسد که نه از نظر UI و نه از نظر کوئری قابل مدیریت منطقی نیست. ۳ محور
#: (مثلاً رنگ × سایز × جنس) با پروتوتایپ (X25) و بلوپرینت محصول هم‌خوان است.
MAX_OPTION_AXES = 3


class VariantEngineError(Exception):
    """خطای قابل‌نمایش هنگام مدیریت محور/مقدار/تولید تنوع چندمحوره."""


@dataclass
class VariantGenerationResult:
    created: list = field(default_factory=list)
    preserved: list = field(default_factory=list)
    obsoleted: list = field(default_factory=list)


def _has_legacy_variants(product: Product) -> bool:
    return product.variants.filter(combination_key="").exists()


def _has_engine_variants(product: Product) -> bool:
    return product.variants.exclude(combination_key="").exists()


@transaction.atomic
def add_product_option(
    product: Product, *, label: str, attribute=None, values: list[str] | None = None,
    input_type: str = ProductOption.InputType.TEXT, color_hex_by_label: dict[str, str] | None = None,
) -> ProductOption:
    """یک محور تنوع جدید به کالا اضافه می‌کند، به‌همراه مقادیر اولیه‌ی اختیاری."""
    label = normalize_text(label)
    if not label:
        raise VariantEngineError("عنوان محور نمی‌تواند خالی باشد.")
    if _has_legacy_variants(product):
        raise VariantEngineError(
            "این کالا هنوز تنوع‌های تک‌محوره‌ی قدیمی دارد؛ ابتدا همه را حذف کنید تا بتوان از "
            "موتور محور/مقدار چندمحوره استفاده کرد."
        )
    if attribute is not None and attribute.store_id != product.store_id:
        raise VariantEngineError("این ویژگی متعلق به فروشگاه دیگری است.")
    if attribute is not None and not attribute.is_variant_axis:
        raise VariantEngineError(f"ویژگی «{attribute.label}» برای محور تنوع مجاز نیست.")

    active_axis_count = product.options.filter(is_active=True).count()
    if active_axis_count >= MAX_OPTION_AXES:
        raise VariantEngineError(f"یک کالا حداکثر می‌تواند {MAX_OPTION_AXES} محور تنوع فعال داشته باشد.")

    last_position = product.options.order_by("-position").values_list("position", flat=True).first()
    next_position = (last_position + 1) if last_position is not None else 0
    option = ProductOption(
        product=product, attribute=attribute, label=label, position=next_position,
        input_type=input_type or ProductOption.InputType.TEXT,
    )
    try:
        option.full_clean()
    except ValidationError as exc:
        raise VariantEngineError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    option.save()

    color_hex_by_label = color_hex_by_label or {}
    for value_label in (values or []):
        add_option_value(option, value_label, color_hex=color_hex_by_label.get(value_label, ""))

    return option


@transaction.atomic
def add_option_value(option: ProductOption, label: str, *, color_hex: str = "", attribute_value=None) -> ProductOptionValue:
    label = normalize_text(label)
    if not label:
        raise VariantEngineError("برچسب مقدار نمی‌تواند خالی باشد.")
    if attribute_value is not None:
        if option.attribute_id is None or attribute_value.attribute_id != option.attribute_id:
            raise VariantEngineError("این مقدار متعلق به ویژگی مرتبط با این محور نیست.")

    next_order = option.values.count()
    option_value = ProductOptionValue(
        option=option, label=label, color_hex=color_hex, attribute_value=attribute_value,
        display_order=next_order,
    )
    try:
        option_value.full_clean()
    except ValidationError as exc:
        raise VariantEngineError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    option_value.save()
    return option_value


def remove_option_value(option_value: ProductOptionValue) -> None:
    """مقدار محور را حذف می‌کند — فقط اگر هرگز در تولید تنوع استفاده نشده باشد؛ در غیر این
    صورت طبق ADR-21 فقط غیرفعال می‌شود (حذف واقعی موکول به ``generate_variants`` بعدی است)."""
    if option_value.variant_links.exists():
        option_value.is_active = False
        option_value.save(update_fields=["is_active", "updated_at"])
        return
    option_value.delete()


def deactivate_product_option(option: ProductOption) -> ProductOption:
    """محور را غیرفعال می‌کند — طبق ADR-21، خودش هیچ تنوعی را منسوخ نمی‌کند؛ فقط پس از
    فراخوانی صریح ``generate_variants`` بازتولید انجام می‌شود."""
    if option.is_active:
        option.is_active = False
        option.save(update_fields=["is_active", "updated_at"])
    return option


def activate_product_option(option: ProductOption) -> ProductOption:
    if not option.is_active:
        option.is_active = True
        option.save(update_fields=["is_active", "updated_at"])
    return option


@transaction.atomic
def reorder_product_options(product: Product, ordered_ids: list[int]) -> None:
    """ترتیب محورهای تنوع را تنظیم می‌کند.

    دو مرحله‌ای است: چون ``position`` یک UniqueConstraint در سطح Product
    دارد و ``PositiveSmallIntegerField`` است (مقدار منفی مجاز نیست)، نوشتن
    مستقیم موقعیت‌های نهایی می‌تواند در میانه‌ی ``bulk_update`` (که
    ردیف‌به‌ردیف روی SQLite اجرا می‌شود) با موقعیت فعلیِ یک ردیف دیگر تصادم
    کند؛ ابتدا به بازه‌ی موقتِ بزرگ (خیلی فراتر از حداکثر تعداد محور مجاز)
    منتقل می‌شوند تا هرگز با موقعیت واقعیِ ردیف دیگری هم‌پوشانی نداشته
    باشند."""
    options = {o.pk: o for o in product.options.filter(pk__in=ordered_ids)}
    valid_ids = [option_id for option_id in ordered_ids if option_id in options]
    if not valid_ids:
        return

    staging_offset = 1000
    staged = []
    for index, option_id in enumerate(valid_ids):
        option = options[option_id]
        option.position = staging_offset + index
        staged.append(option)
    ProductOption.objects.bulk_update(staged, ["position"])

    final = []
    for position, option_id in enumerate(valid_ids):
        option = options[option_id]
        option.position = position
        final.append(option)
    ProductOption.objects.bulk_update(final, ["position"])


@transaction.atomic
def reorder_option_values(option: ProductOption, ordered_ids: list[int]) -> None:
    values = {v.pk: v for v in option.values.filter(pk__in=ordered_ids)}
    valid_ids = [value_id for value_id in ordered_ids if value_id in values]
    updated = []
    for order, value_id in enumerate(valid_ids):
        value = values[value_id]
        value.display_order = order
        updated.append(value)
    if updated:
        ProductOptionValue.objects.bulk_update(updated, ["display_order"])


def _active_axes(product: Product):
    return list(
        product.options.filter(is_active=True).order_by("position").prefetch_related("values")
    )


def preview_combination_count(product: Product) -> int:
    """تعداد ترکیب‌هایی که ``generate_variants`` تولید/حفظ می‌کند، بدون نوشتن چیزی در دیتابیس."""
    axes = _active_axes(product)
    if not axes:
        return 0
    count = 1
    for axis in axes:
        value_count = sum(1 for v in axis.values.all() if v.is_active)
        count *= value_count
    return count


def _combination_key(option_value_ids: list[int]) -> str:
    return "-".join(str(pk) for pk in sorted(option_value_ids))


@transaction.atomic
def generate_variants(product: Product) -> VariantGenerationResult:
    """محورهای فعال کالا را می‌خواند، حاصل‌ضرب دکارتی را محاسبه، و تنوع‌ها را تطبیق می‌دهد.

    Idempotent: اجرای دوباره بدون تغییر محور/مقدار هیچ چیزی نمی‌سازد یا
    منسوخ نمی‌کند — همه چیز به‌عنوان «حفظ‌شده» گزارش می‌شود. اتمیک: یا کل
    عملیات با موفقیت انجام می‌شود یا هیچ‌کدام از تغییرات ثبت نمی‌شود."""
    if product.product_type != Product.ProductType.VARIABLE:
        raise VariantEngineError("این کالا از نوع «دارای تنوع» نیست.")
    if _has_legacy_variants(product):
        raise VariantEngineError(
            "این کالا هنوز تنوع‌های تک‌محوره‌ی قدیمی دارد؛ موتور چندمحوره برای آن قابل اجرا نیست."
        )

    axes = _active_axes(product)
    if not axes:
        raise VariantEngineError("حداقل یک محور تنوع فعال لازم است.")

    value_lists = []
    for axis in axes:
        active_values = [v for v in axis.values.all() if v.is_active]
        if not active_values:
            raise VariantEngineError(f"محور «{axis.label}» هیچ مقدار فعالی ندارد.")
        value_lists.append(active_values)

    desired: dict[str, list[tuple[ProductOption, ProductOptionValue]]] = {}
    for combo in itertools.product(*value_lists):
        key = _combination_key([v.pk for v in combo])
        desired[key] = list(zip(axes, combo))

    existing_variants = {v.combination_key: v for v in product.variants.exclude(combination_key="")}

    # گیتِ سقفِ تنوع (checkpoint 5A، ADR-69/§17/§28): پس از تولید، تعدادِ
    # تنوع‌هایِ فعالِ این کالا برابرِ ``len(desired)`` می‌شود و بقیه منسوخ.
    # تعدادِ فعالِ کلِ فروشگاه (به‌جز همین کالا) + len(desired) نباید از سقف
    # عبور کند. اتمیک است — اگر عبور کند، *کلِ* تولید رد می‌شود (هیچ ترکیبِ
    # جزئی ساخته نمی‌شود؛ §17).
    from apps.subscriptions.services.entitlement_service import (
        UsageLimitExceeded,
        get_entitlement_limit,
        require_growth_allowed,
    )

    variant_limit = get_entitlement_limit(product.store, "catalog.variants")
    if variant_limit is not None:
        require_growth_allowed(product.store)
        store_active = ProductVariant.objects.filter(
            store=product.store, is_active=True, is_obsolete=False,
        ).count()
        this_product_active = product.variants.filter(is_active=True, is_obsolete=False).count()
        resulting = store_active - this_product_active + len(desired)
        if resulting > variant_limit:
            raise UsageLimitExceeded(
                "catalog.variants", limit=variant_limit, current=store_active,
                message=(
                    f"تولیدِ این تنوع‌ها مجموعِ تنوع‌هایِ فعالِ فروشگاه را به {resulting} می‌رساند "
                    f"که از سقفِ پلن ({variant_limit}) بیشتر است."
                ),
            )

    result = VariantGenerationResult()
    ordered_variants: list[ProductVariant] = []

    for key, pairs in desired.items():
        variant = existing_variants.get(key)
        if variant is not None:
            if variant.is_obsolete:
                variant.is_obsolete = False
                variant.is_active = True
                variant.save(update_fields=["is_obsolete", "is_active", "updated_at"])
            result.preserved.append(variant)
            ordered_variants.append(variant)
            continue

        attribute_labels = [axis.label for axis, _ in pairs]
        value_labels = [value.label for _, value in pairs]
        variant = ProductVariant(
            product=product,
            store=product.store,
            attribute=" / ".join(attribute_labels),
            value=" / ".join(value_labels),
            combination_key=key,
            sku=generate_variant_sku(product, "-".join(value_labels)),
            stock=0,
            extra_price=0,
            is_active=True,
        )
        variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
        variant.save()
        VariantOptionValue.objects.bulk_create([
            VariantOptionValue(variant=variant, option=axis, option_value=value) for axis, value in pairs
        ])
        result.created.append(variant)
        ordered_variants.append(variant)

    for key, variant in existing_variants.items():
        if key not in desired and not variant.is_obsolete:
            variant.is_obsolete = True
            variant.is_active = False
            variant.save(update_fields=["is_obsolete", "is_active", "updated_at"])
            result.obsoleted.append(variant)

    to_update = []
    for order, variant in enumerate(ordered_variants):
        if variant.display_order != order:
            variant.display_order = order
            to_update.append(variant)
    if to_update:
        ProductVariant.objects.bulk_update(to_update, ["display_order"])

    _ensure_default_variant(product)

    return result


@transaction.atomic
def add_manual_variant(product: Product, option_value_ids: dict[int, int]) -> ProductVariant:
    """یک ردیفِ تنوعِ چندمحوره را دستی (بدونِ حاصل‌ضربِ دکارتیِ کامل) اضافه/بازیابی می‌کند.

    برایِ دکمه‌ی «+ اضافه کردنِ تنوعِ محصول»: مدیرِ فروشگاه برایِ هر محورِ فعال
    یک مقدار انتخاب می‌کند و فقط همان یک ترکیب ساخته می‌شود — برخلافِ
    ``generate_variants`` که همه‌ی ترکیب‌هایِ ممکن را می‌سازد. ``combination_key``
    دقیقاً با همان قاعده محاسبه می‌شود تا با تولیدِ دسته‌ای بعدی سازگار بماند
    (هرگز دوباره ساخته یا تکراری نمی‌شود)."""
    axes = _active_axes(product)
    if not axes:
        raise VariantEngineError("حداقل یک محور تنوع فعال لازم است.")

    pairs = []
    for axis in axes:
        value_id = option_value_ids.get(axis.pk)
        if not value_id:
            raise VariantEngineError(f"برایِ محورِ «{axis.label}» یک مقدار انتخاب کنید.")
        value = next((v for v in axis.values.all() if v.pk == value_id and v.is_active), None)
        if value is None:
            raise VariantEngineError(f"مقدارِ انتخاب‌شده برایِ محورِ «{axis.label}» معتبر نیست.")
        pairs.append((axis, value))

    key = _combination_key([v.pk for _, v in pairs])
    existing = product.variants.filter(combination_key=key).first()
    if existing is not None:
        if existing.is_obsolete or not existing.is_active:
            existing.is_obsolete = False
            existing.is_active = True
            existing.save(update_fields=["is_obsolete", "is_active", "updated_at"])
        return existing

    attribute_labels = [axis.label for axis, _ in pairs]
    value_labels = [value.label for _, value in pairs]
    variant = ProductVariant(
        product=product,
        store=product.store,
        attribute=" / ".join(attribute_labels),
        value=" / ".join(value_labels),
        combination_key=key,
        sku=generate_variant_sku(product, "-".join(value_labels)),
        stock=0,
        extra_price=0,
        is_active=True,
        display_order=product.variants.count(),
    )
    variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
    variant.save()
    VariantOptionValue.objects.bulk_create([
        VariantOptionValue(variant=variant, option=axis, option_value=value) for axis, value in pairs
    ])
    _ensure_default_variant(product)
    return variant


def _ensure_default_variant(product: Product) -> None:
    """اگر هیچ تنوع فعال/غیرمنسوخی پیش‌فرض نباشد، اولین تنوع (طبق ترتیب نمایش) را پیش‌فرض می‌کند."""
    eligible = product.variants.filter(is_active=True, is_obsolete=False)
    if eligible.filter(is_default=True).exists():
        return
    first = eligible.order_by("display_order", "id").first()
    if first is not None:
        set_default_variant(product, first)


@transaction.atomic
def set_default_variant(product: Product, variant: ProductVariant) -> ProductVariant:
    """این تنوع را پیش‌فرض کالا می‌کند؛ پیش‌فرض قبلی (اگر باشد) خودکار پس گرفته می‌شود.

    الگوی «ربودن پرچم» — دقیقاً مثل ``product_image_service.set_cover_image``."""
    if variant.product_id != product.pk:
        raise VariantEngineError("این تنوع متعلق به کالای دیگری است.")
    if not variant.is_active or variant.is_obsolete:
        raise VariantEngineError("یک تنوع غیرفعال یا منسوخ نمی‌تواند پیش‌فرض باشد.")

    product.variants.exclude(pk=variant.pk).filter(is_default=True).update(is_default=False)
    if not variant.is_default:
        variant.is_default = True
        variant.save(update_fields=["is_default", "updated_at"])
    return variant
