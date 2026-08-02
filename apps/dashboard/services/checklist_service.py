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
    """«انتشار فروشگاه» فقط وقتی واقعاً تکمیل‌شده حساب می‌شود که فروشگاه
    واقعاً چیزی برای فروش داشته باشد — نه صرفِ عبور از ویزاردِ آنبوردینگ.
    پیش از این، این مرحله فقط ``onboarding_completed_at`` را می‌خواند که
    می‌توانست هم‌زمان با ناتمام‌بودنِ مرحله‌ی «ارسال» درست پیش از آن، ✅
    نشان دهد — تناقضی که با این سه‌شرطِ داده‌محور رفع می‌شود: اطلاعاتِ
    پایه‌ی فروشگاه، دست‌کم یک کالای فعال، و دست‌کم یک روشِ ارسال."""
    return (
        _store_information_complete(store, shop)
        and _product_publish_complete(store, shop)
        and _shipping_complete(store, shop)
    )


def _industry_installation(store):
    return (
        StoreIndustryInstallation.objects.select_related("industry_template")
        .filter(store=store)
        .first()
    )


def build_industry_summary(store) -> dict:
    """اطلاعاتِ واقعیِ صنف/قالبِ نصب‌شده برایِ کارتِ کوچکِ «صنفِ فروشگاه» در
    داشبورد — مستقیماً از ``StoreIndustryInstallation`` (تنها منبعِ حقیقتِ
    این داده)؛ اگر نصبی وجود نداشته باشد (چه صنف اصلاً انتخاب نشده باشد، چه
    آگاهانه رد شده باشد)، ``installation`` خالی برمی‌گردد تا تمپلیت پیامِ
    «هنوز قالب صنفی نصب نشده است» را نشان دهد — هیچ متنی این‌جا هاردکد
    نمی‌شود، فقط داده خوانده می‌شود."""
    installation = _industry_installation(store)
    if installation is None:
        return {"has_installation": False}
    return {
        "has_installation": True,
        "industry_name": installation.industry_template.name,
        "template_version": installation.installed_version,
        "status": installation.status,
        "status_label": installation.get_status_display(),
        "installed_at": installation.created_at,
        "categories_created": installation.categories_created,
        "attributes_created": installation.attributes_created,
    }


@dataclass(frozen=True)
class _ChecklistStep:
    key: str
    label: str
    icon: str
    is_complete: Callable
    url: Callable
    description: str = ""


#: کلیدهای زنجیره‌ی اصلیِ ۱۲مرحله‌ای (چک‌لیستِ راه‌اندازیِ کاتالوگ) — نگاه
#: کنید به ``_progressive_unlock`` — هر مرحله فقط وقتی «باز» نمایش داده
#: می‌شود که همه‌ی مراحلِ پیش از خودش در همین فهرست تکمیل شده باشند؛ این
#: قفلِ سخت‌گیرانه‌ی ناوبری نیست (هر مرحله همیشه قابل‌کلیک می‌ماند)، فقط یک
#: نشانه‌ی بصریِ «ابتدا این‌ها را تمام کنید».
CATALOG_CHAIN_KEYS = [
    "industry", "industry_template", "product_groups", "product_categories",
    "brands", "attributes", "first_product", "product_images", "variants",
    "inventory", "shipping", "publish",
]


def _steps():
    return [
        # --- زنجیره‌ی پیش‌نیازیِ واقعیِ ساختِ کالا — دقیقاً ۱۲ مرحله، طبقِ
        # ترتیبِ الزامیِ درخواست: صنف → قالب صنف → گروه‌های دسته‌بندی →
        # دسته‌بندی‌ها → برندها → ویژگی‌ها → اولین کالا → تصاویر → تنوع‌ها →
        # موجودی → ارسال → انتشار فروشگاه. هرگز نباید بدونِ عبور از
        # پیش‌نیازهایش به «اولین کالا» برسد.
        _ChecklistStep(
            "industry", "انتخاب صنف", "🏭", _industry_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=industry",
        ),
        _ChecklistStep(
            "industry_template", "نصب قالب صنف", "🏗️", _industry_template_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=industry",
        ),
        _ChecklistStep(
            "product_groups", "ایجاد گروه‌های دسته‌بندی", "🗂️", _product_groups_complete,
            lambda store, request: reverse("dashboard:category-list"),
        ),
        _ChecklistStep(
            "product_categories", "ایجاد دسته‌بندی‌ها", "📁", _product_subcategories_complete,
            lambda store, request: reverse("dashboard:category-list"),
        ),
        _ChecklistStep(
            "brands", "ایجاد برندها", "🔖", _brands_complete,
            lambda store, request: reverse("dashboard:brand-list"),
        ),
        _ChecklistStep(
            "attributes", "ایجاد ویژگی‌های کالا", "🏷️", _attributes_complete,
            lambda store, request: reverse("dashboard:attribute-list"),
        ),
        _ChecklistStep(
            "first_product", "ایجاد اولین کالا", "📦", _first_product_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        _ChecklistStep(
            "product_images", "بارگذاری تصاویر", "🖼️", _product_images_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        _ChecklistStep(
            "variants", "تنظیم تنوع‌ها", "🎛️", _variants_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
        _ChecklistStep(
            "inventory", "موجودی", "📊", _inventory_complete,
            lambda store, request: reverse("dashboard:inventory-list"),
        ),
        _ChecklistStep(
            "shipping", "پیکربندی ارسال", "🚚", _shipping_complete,
            lambda store, request: reverse("dashboard:shipping-method-list"),
            description="حداقل یک روش ارسال یا گزینه‌ی دریافت حضوری ایجاد کنید.",
        ),
        _ChecklistStep(
            "publish", "انتشار فروشگاه", "🚀", _publish_complete,
            lambda store, request: _platform_url(
                request, f"/app/stores/{store.public_id}/onboarding/review/"
            ),
        ),
        # --- مراحلِ تکمیلیِ راه‌اندازیِ فروشگاه — بخشی از ۱۲ مرحله‌ی الزامی
        # نیستند، اما حذف‌شان نقضِ «عدمِ حذفِ قابلیتِ موجود» بود؛ بعد از
        # زنجیره‌ی اصلی نمایش داده می‌شوند.
        _ChecklistStep(
            "product_publish", "انتشار کالا (فعال‌سازی)", "✅", _product_publish_complete,
            lambda store, request: reverse("dashboard:product-list"),
        ),
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
            "payment_gateway", "درگاه پرداخت", "💳", _payment_gateway_complete,
            lambda store, request: reverse("dashboard:settings") + "?section=payment-config",
        ),
        _ChecklistStep(
            "tax", "اطلاعات مالیاتی", "🧾", _tax_complete,
            lambda store, request: reverse("dashboard:tax-settings"),
        ),
        _ChecklistStep(
            "custom_domain", "دامنه‌ی اختصاصی (اختیاری)", "🌐", _custom_domain_complete,
            lambda store, request: _platform_url(request, f"/app/stores/{store.public_id}/domains/"),
            description="اختیاری — فروشگاه بدونِ دامنه‌ی اختصاصی هم روی زیردامنه‌ی راستیسی کاملاً در دسترس است.",
        ),
    ]


def build_setup_checklist(store, request):
    """چک‌لیستِ راه‌اندازی برایِ داشبوردِ خانه — هر بار زنده محاسبه می‌شود،
    هیچ‌جا ذخیره نمی‌شود.

    ``is_unlocked`` یک نشانه‌ی صرفاً بصری است، نه یک قفلِ ناوبری: مرحله‌ای
    از زنجیره‌ی اصلیِ کاتالوگ (``CATALOG_CHAIN_KEYS``) تا وقتی همه‌ی
    مراحلِ پیش از خودش در همان زنجیره تکمیل نشده باشند «قفل» نشان داده
    می‌شود — اما دکمه‌اش همچنان کلیک‌پذیر می‌ماند، چون مدیرِ فروشگاه باید
    همیشه بتواند آزادانه هر صفحه‌ای را باز کند؛ این فقط ترتیبِ پیشنهادی را
    نشان می‌دهد. مراحلِ تکمیلی (خارج از این زنجیره) همیشه باز هستند."""
    shop = _shop_settings(store)
    steps = []
    completed_count = 0
    chain_blocked_so_far = False
    blocking_label = None
    next_step_key = None
    for step in _steps():
        is_complete = bool(step.is_complete(store, shop))
        if is_complete:
            completed_count += 1
        in_chain = step.key in CATALOG_CHAIN_KEYS
        is_unlocked = not (in_chain and chain_blocked_so_far)
        locked_reason = (
            f"ابتدا «{blocking_label}» را تکمیل کنید" if in_chain and not is_unlocked else ""
        )
        if next_step_key is None and not is_complete and is_unlocked:
            next_step_key = step.key
        if in_chain and not is_complete:
            if not chain_blocked_so_far:
                blocking_label = step.label
            chain_blocked_so_far = True
        steps.append({
            "key": step.key,
            "label": step.label,
            "icon": step.icon,
            "is_complete": is_complete,
            "is_unlocked": is_unlocked,
            "locked_reason": locked_reason,
            "is_next": step.key == next_step_key,
            "url": step.url(store, request),
            "description": step.description,
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
