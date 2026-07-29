"""موتورِ محاسبه‌ی ارسال — منطقه‌بندی، انتخابِ روشِ ارسال، محاسبه‌ی نرخ.

نگاه کنید به ADR-41 (اولویتِ تطبیقِ منطقه)، ADR-42 (اولویتِ قواعدِ نرخ)،
ADR-43 (بازمحاسبه‌ی سمتِ سرور در تسویه‌حساب) در ``SAAS_DOMAIN_DECISIONS.md``.

هیچ تابعی این‌جا به ``request`` وابسته نیست — همه‌چیز صریح از پارامتر
گرفته می‌شود؛ این ماژول هرگز مستقیماً View نیست، فقط منطقِ دامنه‌ی خالص.

سازگاریِ پیش‌رونده (backward-compatible): وقتی یک ``ShippingMethod`` هیچ
``ShippingRateRule`` فعالی ندارد — دقیقاً وضعیتِ هر ``ShippingMethod``ی که
پیش از checkpoint 3B ساخته شده — محاسبه‌ی نرخ به رفتارِ قدیمیِ
``ShippingMethod.cost``/``free_over`` بازمی‌گردد، بدونِ کوچک‌ترین تغییر."""

from decimal import Decimal

from django.utils import timezone

from apps.orders.models import ShippingMethod, ShippingRateRule, ShippingZone


def resolve_shipping_zone(store, *, province: str = "", city: str = "", postal_code: str = "") -> ShippingZone | None:
    """بهترین منطقه‌ی تطبیق‌یافته را طبقِ سیاستِ اولویتِ ADR-41 برمی‌گرداند:
    تطبیقِ دقیقِ کدپستی > شهر > استان > منطقه‌ی پیش‌فرض/ذخیره > هیچ تطبیقی.

    این کدبیس فیلدِ کشور ندارد (فقط ایران) پس آن لایه از سلسله‌مراتب حذف
    شده — نه اختراعِ زیرساختِ جغرافیاییِ پشتیبانی‌نشده."""
    zones = list(ShippingZone.objects.filter(store=store, is_active=True))

    def _best(candidates):
        matching = [z for z in candidates if z.matches(province=province, city=city, postal_code=postal_code)]
        if not matching:
            return None
        return sorted(matching, key=lambda z: (z.priority, z.pk))[0]

    if postal_code:
        postal_matches = [z for z in zones if postal_code in z.postal_codes]
        found = _best(postal_matches)
        if found is not None:
            return found

    if city:
        city_matches = [z for z in zones if city in z.cities]
        found = _best(city_matches)
        if found is not None:
            return found

    if province:
        province_matches = [z for z in zones if province in z.provinces]
        found = _best(province_matches)
        if found is not None:
            return found

    fallback = [z for z in zones if z.is_fallback]
    if fallback:
        return sorted(fallback, key=lambda z: (z.priority, z.pk))[0]

    return None


def get_available_shipping_methods(store, *, province: str = "", city: str = "", postal_code: str = ""):
    """روش‌های فعالِ این Store که برای این مقصد در دسترس‌اند.

    روشِ بدونِ منطقه (``zone=None``) همیشه سراسری و در دسترس است — دقیقاً
    رفتارِ هر ``ShippingMethod`` موجود پیش از این چک‌پوینت، چون فیلدِ
    ``zone`` جدید است و پیش‌فرضش None. روشِ دارای منطقه فقط وقتی در دسترس
    است که مقصد با همان منطقه تطبیق داشته باشد."""
    zone = resolve_shipping_zone(store, province=province, city=city, postal_code=postal_code)
    methods = ShippingMethod.objects.filter(store=store, is_active=True).select_related("zone", "pickup_warehouse")

    available = []
    for method in methods:
        if method.zone_id is None:
            available.append(method)
        elif zone is not None and method.zone_id == zone.pk:
            available.append(method)
    return available


def resolve_best_rate_rule(method: ShippingMethod, *, subtotal: Decimal, weight_grams: int = 0) -> ShippingRateRule | None:
    """قاعده‌ی نرخِ برنده برای این روش را طبقِ ADR-42 برمی‌گرداند: اولویتِ
    عددیِ کوچک‌تر برنده، سپس قاعده‌ی محدودتر (specificity بیشتر)، سپس شناسه‌ی
    پایدار (pk) برای شکستنِ تساویِ نهایی. اگر هیچ قاعده‌ی فعال/در-بازه‌ای
    وجود نداشته باشد، ``None`` برمی‌گرداند — فراخواننده باید به
    ``method.cost``/``free_over`` بازگردد."""
    now = timezone.now()
    candidates = [
        rule for rule in method.rate_rules.filter(is_active=True)
        if (rule.start_at is None or rule.start_at <= now) and (rule.end_at is None or rule.end_at >= now)
        and rule.matches(subtotal=subtotal, weight_grams=weight_grams)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda r: (r.priority, -r.specificity, r.pk))[0]


def calculate_shipping_rate(method: ShippingMethod, *, subtotal: Decimal, weight_grams: int = 0) -> Decimal:
    """نرخِ نهاییِ ارسال برای این روش با این جمع‌سبد/وزن.

    اگر قاعده‌ی نرخِ فعالی تطبیق داشته باشد از آن استفاده می‌شود (با آستانه‌ی
    ارسالِ رایگانِ اختصاصیِ همان قاعده در صورتِ وجود)؛ در غیرِ این صورت
    رفتارِ قدیمیِ ``method.cost`` بدونِ تغییر اجرا می‌شود."""
    if method.method_type == ShippingMethod.MethodType.FREE:
        return Decimal("0")

    rule = resolve_best_rate_rule(method, subtotal=subtotal, weight_grams=weight_grams)
    if rule is not None:
        if rule.free_over is not None and subtotal >= rule.free_over:
            return Decimal("0")
        return rule.rate_amount

    return method.cost


def cart_shippable_weight_grams(items) -> int:
    """مجموعِ وزنِ اقلامی از سبد/سفارش که ``requires_shipping=True`` دارند.

    وزنِ گمشده (نه Variant نه Product مقداری برای وزن ندارند) صفر در نظر
    گرفته می‌شود — این بازگشتِ صریح و مستندشده است، نه پذیرشِ خاموشِ یک
    ورودیِ نامعتبر (نگاه کنید به بخشِ «سیاستِ وزن» در گزارش)."""
    total = 0
    for item in items:
        product = item.product
        if product is None or not product.requires_shipping:
            continue
        variant = getattr(item, "variant", None)
        if variant is not None and variant.weight_grams is not None:
            total += variant.weight_grams * item.quantity
        elif product.weight_grams is not None:
            total += product.weight_grams * item.quantity
    return total


def cart_requires_shipping(items) -> bool:
    """آیا حداقل یک قلمِ این سبد/سفارش نیازِ ارسالِ فیزیکی دارد — سبدِ کاملاً
    دیجیتال هرگز نباید انتخابِ روشِ ارسال را الزامی کند."""
    return any(item.product is not None and item.product.requires_shipping for item in items)
