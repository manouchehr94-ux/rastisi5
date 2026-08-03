"""داده‌ی نمایشیِ انتخابِ تنوع در فروشگاه — محورهایِ *مستقل* (independent
per-axis selectors)، نه یک انتخاب‌گرِ ترکیبیِ واحد.

این ماژول به موتورِ تنوعِ چندمحوره (``variant_engine_service``) دست
نمی‌زند؛ فقط داده‌ی همان مدل‌ها (``ProductOption``/``ProductOptionValue``/
``VariantOptionValue`` برایِ کالاهایِ چندمحوره، یا ``ProductVariant.attribute``/
``.value`` برایِ کالاهایِ تک‌محورِ قدیمی) را به شکلی می‌سازد که قالب/Alpine.js
بتواند بدونِ بارگذاریِ مجددِ صفحه، با انتخابِ هر مقدار در هر محور، دقیقاً یک
تنوعِ واقعی را پیدا کند.

Part 7 (مشخصات): «هر محور باید انتخاب‌گرِ مستقلِ خودش را داشته باشد» —
کالاهایِ چندمحوره (مثلاً رنگ × سایز) دیگر به‌صورتِ یک رشته‌ی ترکیبیِ واحد
(«رنگ / سایز» → «قرمز / بزرگ») نمایش داده نمی‌شوند.
"""

from apps.catalog.services.pricing_service import (
    is_variant_purchasable,
    resolve_effective_price,
    resolve_regular_price,
    resolve_savings,
)


def resolve_display_image(product, variant, option_value_ids=None):
    """اولویتِ تصویر (Part 8): ۱) تصویرِ دقیقِ همین تنوع، ۲) تصویرِ اختصاص‌یافته
    به یکی از مقادیرِ ویژگیِ تصویرمحورِ این ترکیب (مثلاً رنگ)، ۳) کاورِ کالا.

    مرحله‌ی دوم فقط برایِ تنوع‌هایِ چندمحوره (دارایِ ``VariantOptionValue``)
    معنا دارد. تکِ منبعِ حقیقتِ این اولویت — هم فروشگاه (این ماژول) و هم
    جدولِ «پیکربندیِ تنوع‌ها»یِ پنلِ مدیریت (``ProductVariant.display_image``)
    باید همین تابع را صدا بزنند، نه یک نسخه‌ی موازیِ ناقص."""
    images = list(variant.images.all())
    if images:
        return images[0]
    if option_value_ids:
        for image in product.images.all():
            if image.option_value_id in option_value_ids:
                return image
    return product.cover_image


def _variant_payload(product, variant, option_value_ids=None):
    image = resolve_display_image(product, variant, option_value_ids)
    return {
        "variant_id": variant.pk,
        "sku": variant.sku,
        "barcode": variant.barcode,
        "price": int(resolve_effective_price(product, variant)),
        "regular_price": int(resolve_regular_price(product, variant)),
        "savings": int(resolve_savings(product, variant)),
        "stock": variant.stock,
        "is_active": variant.is_active,
        "is_purchasable": is_variant_purchasable(variant),
        "image_url": image.image.url if image else "",
        "thumb_url": (image.thumbnail.url if image.thumbnail else image.image.url) if image else "",
    }


def _multi_axis_context(product, variants):
    axes_qs = list(
        product.options.filter(is_active=True).order_by("position").prefetch_related("values")
    )
    axes = []
    for axis in axes_qs:
        values = [
            {
                "id": value.pk,
                "label": value.label,
                "color_hex": value.color_hex,
                "swatch_image_url": (
                    value.attribute_value.swatch_image.url
                    if value.attribute_value_id and value.attribute_value.swatch_image
                    else ""
                ),
            }
            for value in axis.values.all() if value.is_active
        ]
        axes.append({"id": axis.pk, "label": axis.label, "values": values})

    axis_order = [axis["id"] for axis in axes]
    matrix = {}
    default_key = None
    default_variant = (
        variants.filter(is_default=True).first()
        or variants.order_by("display_order", "id").first()
    )
    for variant in variants.prefetch_related("option_values__option", "option_values__option_value"):
        value_by_axis = {link.option_id: link.option_value_id for link in variant.option_values.all()}
        try:
            key = "|".join(str(value_by_axis[axis_id]) for axis_id in axis_order)
        except KeyError:
            # این تنوع محورهایی خارج از محورهایِ فعلاً فعال دارد (مثلاً
            # منسوخ‌شده) — در ماتریسِ انتخابِ فروشگاه نمایش داده نمی‌شود.
            continue
        matrix[key] = _variant_payload(product, variant, option_value_ids=set(value_by_axis.values()))
        if default_variant is not None and variant.pk == default_variant.pk:
            default_key = key

    return {
        "mode": "multi_axis",
        "axes": axes,
        "matrix": matrix,
        "groups": [],
        "default_key": default_key,
    }


def _legacy_context(product, variants):
    groups_by_attribute = {}
    order = []
    default_variant = (
        variants.filter(is_default=True).first()
        or variants.order_by("display_order", "id").first()
    )
    default_key = str(default_variant.pk) if default_variant else None

    for variant in variants.order_by("display_order", "attribute", "value"):
        if variant.attribute not in groups_by_attribute:
            groups_by_attribute[variant.attribute] = []
            order.append(variant.attribute)
        payload = _variant_payload(product, variant)
        payload.update({"id": variant.pk, "label": variant.value, "color_hex": variant.value_hex})
        groups_by_attribute[variant.attribute].append(payload)

    groups = [{"label": attribute, "values": groups_by_attribute[attribute]} for attribute in order]

    return {
        "mode": "legacy",
        "axes": [],
        "matrix": {},
        "groups": groups,
        "default_key": default_key,
    }


def build_variant_selector_context(product):
    """داده‌ی کاملِ لازم برایِ انتخابِ تنوعِ فروشگاه را می‌سازد — قابلِ
    ``json.dumps`` مستقیم برایِ جاسازی در قالب (``json_script``)."""
    variants = product.variants.filter(is_active=True, is_obsolete=False)
    if not variants.exists():
        return {"mode": "none", "axes": [], "matrix": {}, "groups": [], "default_key": None}

    has_engine_axes = product.options.filter(is_active=True).exists()
    has_engine_variants = variants.exclude(combination_key="").exists()
    if has_engine_axes and has_engine_variants:
        return _multi_axis_context(product, variants)
    return _legacy_context(product, variants)
