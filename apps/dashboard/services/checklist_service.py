"""چک‌لیست راه‌اندازی فروشگاه (Store Setup Checklist) — تشخیص خودکار وضعیت
تکمیل هر مرحله مستقیماً از داده‌ی واقعیِ سیستم، بدون هیچ فیلد/مدلِ جداگانه‌ی
«انجام‌شده/نشده». هر بررسی همان مدل/سرویسی را می‌خواند که خودِ صفحه‌ی مربوطه
برای نمایش وضعیتش استفاده می‌کند (ShopSettings، Category، Attribute، Brand،
Product، ProductImage، ProductVariant، ShippingMethod، PaymentGatewayConfig،
TaxRate، StoreDomain، StoreIndustryInstallation، publication_service) — این
ماژول چیزی تولید یا ذخیره نمی‌کند، فقط می‌پرسد.

ترتیبِ مراحلِ کاتالوگ (صنف → قالب صنف → گروه‌های کالا → دسته‌بندی/زیردسته →
ویژگی‌ها → برندها → اولین کالا → تصاویر → تنوع‌ها → موجودی → انتشار کالا)
عمداً همان زنجیره‌ی واقعیِ پیش‌نیازیِ ساختِ یک کالا را دنبال می‌کند — «اولین
کالا» هرگز نباید پیش از پیش‌نیازهایش (دسته‌بندی/ویژگی/برند) نمایش داده شود."""

from dataclasses import dataclass
from typing import Callable

from django.conf import settings as django_settings
from django.urls import reverse

from apps.catalog.models import Attribute, Brand, Category, Product, ProductImage, ProductVariant, StoreIndustryInstallation
from apps.core.models import ShopSettings, ShopSettingsNotProvisionedError
from apps.orders.models import PaymentGatewayConfig, ShippingMethod, TaxRate
from apps.stores.models import Store, StoreDomain

#: مقادیرِ پیش‌فرضِ رنگِ ShopSettings (دقیقاً همان‌هایی که در تعریفِ مدل
#: آمده‌اند) — «تم» وقتی تکمیل‌شده حساب می‌شود که دست‌کم یکی از رنگ‌ها از
#: پیش‌فرضش تغییر کرده باشد، چون فیلدِ صریحِ «تم سفارشی‌سازی شد؟» وجود ندارد.
_DEFAULT_COLORS = {
    "primary_color": "#6D28D9",
    "accent_color": "#FF4D77",
    "secondary_color": "#7C3AED",
    "background_color": "#F7F5FC",
    "surface_color": "#FFFFFF",
    "text_color": "#241C3A",
    "muted_text_color": "#8B86A3",
}


def _shop_settings(store):
    try:
        return ShopSettings.load(store=store)
    except ShopSettingsNotProvisionedError:
        return None


def _platform_url(request, path):
    """آدرسِ مطلقِ روی میزبانِ پرتالِ مالک — همان الگویی که
    ``apps.dashboard.context_processors.platform_link`` برایِ لینکِ «بازگشت
    به راستیسی» استفاده می‌کند؛ چون این صفحات (اتصالِ دامنه، انتشارِ
    فروشگاه) در اپ ``apps.portal`` هستند، نه در پنلِ مدیریتِ همین Store."""
    return f"{request.scheme}://{django_settings.RASTISI_PLATFORM_PRIMARY_HOST}{path}"


def _store_information_complete(store, shop):
    return bool(shop and shop.description.strip())


def _industry_decided(store):
    """صنفِ فروشگاه «تصمیم‌گیری‌شده» است — یا واقعاً یک قالب نصب شده، یا مالک
    آگاهانه این مرحله را در ویزاردِ آنبوردینگ رد کرده (Section 5، ADR-25 —
    انتخابِ صنف اختیاری و رد-شدنی است). ``onboarding_stage`` فقط وقتی از
    INDUSTRY عبور می‌کند که یکی از این دو رخ داده باشد؛ پس همین یک فیلد،
    بدونِ نیاز به مدلِ جداگانه‌ی «صنف انتخاب شد اما نصب نشد»، هر دو حالت را
    به‌درستی پوشش می‌دهد."""
    if StoreIndustryInstallation.objects.filter(store=store).exists():
        return True
    return store.onboarding_stage not in (Store.OnboardingStage.IDENTITY, Store.OnboardingStage.INDUSTRY)


def _industry_complete(store, shop):
    return _industry_decided(store)


def _industry_template_complete(store, shop):
    """«نصب قالب صنف» — اگر مالک صنف را رد کرده (نه انتخاب)، این مرحله
    اساساً منتفی است، نه ناتمام؛ پس با عبور از تصمیمِ صنف، این مرحله هم
    تکمیل‌شده حساب می‌شود (نگاه کنید به ``_industry_decided``)."""
    return _industry_decided(store)


def _product_groups_complete(store, shop):
    """«گروه‌های کالا» = دسته‌بندیِ سطحِ اول (بدون والد) — نگاه کنید به
    برچسبِ ناوبریِ موجود «گروه‌بندی کالاها» که دقیقاً همین Category را نشان
    می‌دهد."""
    return Category.objects.filter(store=store, parent__isnull=True).exists()


def _product_subcategories_complete(store, shop):
    """کالا فقط می‌تواند به یک زیردسته (نه دسته‌ی سطحِ اول) وصل شود —
    نگاه کنید به ``leaf_categories`` در catalog_admin_service — پس این
    همان پیش‌نیازِ واقعیِ «اولین کالا» ست، نه صرفِ وجودِ هر دسته‌ای."""
    return Category.objects.filter(store=store, parent__isnull=False).exists()


def _attributes_complete(store, shop):
    return Attribute.objects.filter(store=store).exists()


def _brands_complete(store, shop):
    return Brand.objects.filter(store=store).exists()


def _product_images_complete(store, shop):
    return ProductImage.objects.filter(product__store=store).exists()


def _variants_complete(store, shop):
    return ProductVariant.objects.filter(store=store).exists()


def _inventory_complete(store, shop):
    return Product.objects.filter(store=store, stock__gt=0).exists()


def _product_publish_complete(store, shop):
    return Product.objects.filter(store=store, status=Product.Status.ACTIVE).exists()


def _contact_complete(store, shop):
    return bool(shop and (shop.contact_phone.strip() or shop.contact_email.strip()))


def _logo_complete(store, shop):
    return bool(shop and shop.logo)


def _theme_complete(store, shop):
    if shop is None:
        return False
    return any(getattr(shop, field) != default for field, default in _DEFAULT_COLORS.items())


def _first_product_complete(store, shop):
    return Product.objects.filter(store=store).exists()


def _shipping_complete(store, shop):
    return ShippingMethod.objects.filter(store=store).exists()


def _payment_gateway_complete(store, shop):
    return PaymentGatewayConfig.objects.filter(store=store, is_active=True).exists()


def _tax_complete(store, shop):
    return TaxRate.objects.filter(store=store).exists()


def _custom_domain_complete(store, shop):
    return StoreDomain.objects.filter(
        store=store,
        domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
    ).exists()


def _publish_complete(store, shop):
    return store.onboarding_completed_at is not None


@dataclass(frozen=True)
class _ChecklistStep:
    key: str
    label: str
    icon: str
    is_complete: Callable
    url: Callable


def _steps():
    return [
        # --- زنجیره‌ی پیش‌نیازیِ واقعیِ ساختِ کالا (Section 3 requirement) —
        # ترتیب هرگز نباید بدونِ عبور از پیش‌نیازهایش به «اولین کالا» برسد.
        _ChecklistStep(
            "industry", "صنف فروشگاه", "🏭", _industry_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=industry",
        ),
        _ChecklistStep(
            "industry_template", "نصب قالب صنف", "🏗️", _industry_template_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=industry",
        ),
        _ChecklistStep(
            "product_groups", "گروه‌های کالا", "🗂️", _product_groups_complete,
            lambda store, request: reverse("dashboard:category-list"),
        ),
        _ChecklistStep(
            "product_categories", "دسته‌بندی/زیردسته‌ی کالا", "📁", _product_subcategories_complete,
            lambda store, request: reverse("dashboard:category-list"),
        ),
        _ChecklistStep(
            "attributes", "ویژگی‌های کالا", "🏷️", _attributes_complete,
            lambda store, request: reverse("dashboard:attribute-list"),
        ),
        _ChecklistStep(
            "brands", "برندها", "🔖", _brands_complete,
            lambda store, request: reverse("dashboard:brand-list"),
        ),
        _ChecklistStep(
            "first_product", "اولین کالا", "📦", _first_product_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        _ChecklistStep(
            "product_images", "تصاویر کالا", "🖼️", _product_images_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        _ChecklistStep(
            "variants", "تنوع‌های کالا", "🎛️", _variants_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        _ChecklistStep(
            "inventory", "موجودی کالا", "📊", _inventory_complete,
            lambda store, request: reverse("dashboard:inventory-list"),
        ),
        _ChecklistStep(
            "product_publish", "انتشار کالا", "🚀", _product_publish_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        # --- بقیه‌ی مراحلِ راه‌اندازیِ فروشگاه — بدون تغییر در معنا یا آدرس،
        # فقط بعد از زنجیره‌ی کاتالوگِ بالا.
        _ChecklistStep(
            "store_info", "اطلاعات فروشگاه", "🏬", _store_information_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=general",
        ),
        _ChecklistStep(
            "contact", "اطلاعات تماس", "☎️", _contact_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=general",
        ),
        _ChecklistStep(
            "logo", "لوگو", "🖼️", _logo_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=appearance",
        ),
        _ChecklistStep(
            "theme", "قالب و رنگ‌بندی", "🎨", _theme_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=appearance",
        ),
        _ChecklistStep(
            "shipping", "روش ارسال", "🚚", _shipping_complete,
            lambda store, request: reverse("dashboard:shipping-zone-list"),
        ),
        _ChecklistStep(
            "payment_gateway", "درگاه پرداخت", "💳", _payment_gateway_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=payment-config",
        ),
        _ChecklistStep(
            "tax", "اطلاعات مالیاتی", "🧾", _tax_complete,
            lambda store, request: reverse("dashboard:tax-settings"),
        ),
        _ChecklistStep(
            "custom_domain", "دامنه‌ی اختصاصی", "🌐", _custom_domain_complete,
            lambda store, request: _platform_url(request, f"/app/stores/{store.public_id}/domains/"),
        ),
        _ChecklistStep(
            "publish", "انتشار فروشگاه", "🚀", _publish_complete,
            lambda store, request: _platform_url(
                request, f"/app/stores/{store.public_id}/onboarding/review/"
            ),
        ),
    ]


def build_setup_checklist(store, request):
    """چک‌لیستِ راه‌اندازی برایِ داشبوردِ خانه — هر بار زنده محاسبه می‌شود،
    هیچ‌جا ذخیره نمی‌شود."""
    shop = _shop_settings(store)
    steps = []
    completed_count = 0
    for step in _steps():
        is_complete = bool(step.is_complete(store, shop))
        if is_complete:
            completed_count += 1
        steps.append({
            "key": step.key,
            "label": step.label,
            "icon": step.icon,
            "is_complete": is_complete,
            "url": step.url(store, request),
        })
    total_count = len(steps)
    percent = round(completed_count * 100 / total_count) if total_count else 0
    return {
        "steps": steps,
        "completed_count": completed_count,
        "total_count": total_count,
        "percent": percent,
        "all_complete": total_count > 0 and completed_count == total_count,
    }
