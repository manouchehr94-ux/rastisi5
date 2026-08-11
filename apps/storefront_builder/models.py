"""مدل‌های سازنده بصری صفحه فروشگاه — معماری هیبرید (سند نسخه‌بندی‌شده + ارجاع نرمال‌شده).

این معماری دقیقاً مطابق گزینه C توصیه‌شده در
``docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md`` (بخش ۱۰) است و
تصمیمات باز آن گزارش (بخش ۳۲) به این صورت حل شده‌اند:

- هدر، فوتر و بخش‌های صفحه اصلی همگی به یک ``StorefrontLayoutVersion``
  واحد تعلق دارند و یک چرخه‌ی واحدِ Draft/Preview/Publish را به اشتراک
  می‌گذارند (نه یک سیستم نسخه‌بندی جدا برای هدر/فوتر).
- بازگردانی یک نسخه‌ی قدیمی هرگز مستقیماً منتشر نمی‌شود؛ همیشه یک
  Draft جدید می‌سازد (سرویس ``layout_service.restore_version``).
- پرچم فعال‌سازی تدریجی per-store (``uses_visual_storefront_layout``)
  عمداً روی خودِ ``StorefrontLayout`` قرار گرفته، نه روی ``Store`` —
  مدل ``Store`` طبق ADR مستندشده در ``apps/stores/models.py`` عمداً
  حداقلی نگه داشته می‌شود (بدون فیلد تم/ویژگی)؛ این پرچم دقیقاً همان
  الگوی ``ShopSettings``/``FooterSettings`` را دنبال می‌کند: یک مدل
  تنظیمات جداگانه به‌ازای هر Store، نه فیلد مستقیم روی Store.
- نوع هر بخش (``section_key``) در دیتابیس allowlist نمی‌شود؛ اعتبارسنجی
  در برابر Section Registry (``apps/storefront_builder/section_registry.py``)
  همیشه در لایه سرویس انجام می‌شود — مطابق قرارداد کل کدبیس که
  اعتبارسنجی JSONField را همیشه در سرویس انجام می‌دهد نه در ``clean()``.
"""

import hashlib
import json
import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel

#: کلیدهای toggle هدر/فوتر و مقادیر پیش‌فرض‌شان — تک‌منبع حقیقت، هم برای
#: فرم‌های ویرایشگر (views.py) و هم برای رندر (preview/صفحه عمومی). اینجا
#: تعریف شده‌اند (نه فقط در views.py) دقیقاً برای اینکه
#: ``StorefrontLayoutVersion.effective_header_config``/``effective_footer_config``
#: همیشه یک دیکشنری کاملاً پر برگردانند — هرگز کلید ناقص، تا در تمپلیت‌ها
#: هرگز نیازی به ``|default:True`` (که مقدار صریح ``False`` را هم به اشتباه
#: falsy می‌گیرد و override می‌کند) نباشد.
HEADER_TOGGLE_FIELDS = ["show_search", "show_account", "show_cart", "show_wishlist", "sticky", "announcement_enabled"]
HEADER_CONFIG_DEFAULTS = {f: True for f in HEADER_TOGGLE_FIELDS} | {"announcement_text": ""}

FOOTER_TOGGLE_FIELDS = [
    "show_about", "show_contact", "show_quick_links", "show_categories",
    "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter", "show_copyright",
]
FOOTER_CONFIG_DEFAULTS = {f: True for f in FOOTER_TOGGLE_FIELDS}

#: کلیدهایِ رنگِ توکنِ ظاهر — دقیقاً همان مجموعه‌ای که ``tokens.css``ی
#: موجود از قبل به‌عنوانِ ``--brand-*`` مصرف می‌کند (audit شده قبل از
#: نهایی‌کردن؛ نگاه کنید به گزارشِ ممیزی، بخشِ «Site Appearance»)، به‌علاوه
#: ``border`` که امروز فقط derived است (``mix_hex(text, surface)``) و
#: اینجا برایِ اولین‌بار به یک توکنِ قابلِ‌override واقعی تبدیل می‌شود.
APPEARANCE_COLOR_KEYS = ["primary", "secondary", "accent", "background", "surface", "text", "muted", "border"]

#: پیش‌فرض‌هایِ ظاهر — عمداً دقیقاً برابرِ مقادیرِ پیش‌فرضِ فعلیِ
#: ``ShopSettings`` (``apps/core/models.py``) هستند تا فروشگاه‌هایی که
#: هنوز به سیستمِ ظاهرِ نسخه‌بندی‌شده دست نزده‌اند، هیچ تغییرِ بصری‌ای
#: نبینند — دقیقاً همان الزامِ سازگاریِ کاملِ با گذشته که برایِ
#: header_config/footer_config هم رعایت شده.
APPEARANCE_CONFIG_DEFAULTS = {
    "template_slug": "modern",
    "palette_slug": None,
    "color_overrides": {},
    "font": "Vazirmatn",
    "radius": 18,
    "button_radius": 12,
    "density": "normal",
    "motion": "subtle",
    "type_scale": "normal",
    "button_style": "filled",
    "image_fit": "cover",
    "image_hover": "zoom",
    # تنظیماتِ مستقلِ تصویرِ کارتِ محصول (تصمیمِ مالک: crossfade و zoom
    # باید مستقل باشند — یکی دیگری را فعال/غیرفعال نمی‌کند):
    "card_image_crossfade": False,   # نمایشِ تصویرِ دوم هنگامِ hover
    "card_image_zoom": True,         # بزرگ‌نماییِ تصویر هنگامِ hover
    # خانواده‌ی قالب (DOM/Renderer اختصاصی — تصمیمِ مالک Q-01/Q-02،
    # docs/template-references/live-audit/10_OWNER_DECISION_LOG.md) و
    # Presetِ فعالِ درونِ همان خانواده (family_registry.py/preset_registry.py).
    # None یعنی «بدون Family» — همان DOM مشترکِ ۱۰ Template قدیمی، دقیقاً
    # رفتار فعلی، بدون تغییر برای فروشگاه‌هایی که این سیستم را انتخاب
    # نکرده‌اند.
    "family_slug": None,
    "preset_slug": None,
}


class StorefrontLayout(TimeStampedModel):
    """لنگر یک‌به‌یک هر فروشگاه — اشاره‌گر به نسخه‌ی منتشرشده و نسخه‌ی پیش‌نویس.

    انتشار یک عملیات اتمیک است چون فقط همین اشاره‌گرها عوض می‌شوند؛
    محتوای خودِ نسخه از قبل کامل و معتبر است (بخش ۱۴ گزارش ممیزی).
    """

    store = models.OneToOneField(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="storefront_layout",
    )
    uses_visual_storefront_layout = models.BooleanField(
        "استفاده از سازنده بصری", default=False,
        help_text="تا وقتی این فروشگاه اولین نسخه را منتشر نکرده، صفحه اصلی قدیمی (hard-coded) بدون تغییر رندر می‌شود.",
    )
    published_version = models.ForeignKey(
        "StorefrontLayoutVersion", verbose_name="نسخه منتشرشده",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    draft_version = models.ForeignKey(
        "StorefrontLayoutVersion", verbose_name="نسخه پیش‌نویس",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "چیدمان صفحه فروشگاه"
        verbose_name_plural = "چیدمان‌های صفحه فروشگاه"

    def __str__(self):
        return f"چیدمان {self.store.name}"

    @classmethod
    def provision_for(cls, store) -> "StorefrontLayout":
        """رکورد ``StorefrontLayout`` یک Store را می‌سازد؛ اگر از قبل وجود
        داشته باشد دست‌نخورده برمی‌گردد (idempotent) — همان قرارداد
        ``ShopSettings.provision_for``/``FooterSettings.provision_for``."""
        obj, _ = cls.objects.get_or_create(store=store)
        return obj


class StorefrontLayoutVersion(TimeStampedModel):
    """یک نسخه‌ی immutable-پس‌از-انتشار از کل چیدمان (هدر + فوتر + بخش‌ها).

    الگوی نسخه‌بندی دقیقاً مطابق جفت ``IndustryTemplate``/``StoreTemplateUpdate``
    (تنها الگوی rollback-capable موجود در کدبیس پیش از این کار) است:
    هر نسخه پس از publish هرگز mutate نمی‌شود؛ ویرایش بعدی یعنی ساخت
    یک نسخه Draft جدید.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"
        ARCHIVED = "archived", "بایگانی‌شده"

    class Source(models.TextChoices):
        MANUAL = "manual", "ویرایش دستی"
        LEGACY_BOOTSTRAP = "legacy_bootstrap", "برخاسته از صفحه اصلی قدیمی"
        INDUSTRY_TEMPLATE = "industry_template", "قالب صنعتی"
        RESTORED = "restored", "بازگردانی از نسخه قبلی"

    layout = models.ForeignKey(
        StorefrontLayout, verbose_name="چیدمان", on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField("شماره نسخه")
    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT,
    )
    source = models.CharField(
        "منشأ", max_length=20, choices=Source.choices, default=Source.MANUAL,
    )
    label = models.CharField("برچسب", max_length=150, blank=True)

    header_config = models.JSONField("پیکربندی هدر", default=dict, blank=True)
    footer_config = models.JSONField("پیکربندی فوتر", default=dict, blank=True)
    appearance_config = models.JSONField(
        "پیکربندی ظاهر", default=dict, blank=True,
        help_text=(
            "قالب/پالت/فونت/گردی/تراکم/حرکت — دقیقاً همان الگویِ header_config/"
            "footer_config (JSON روی خودِ نسخه) تا تغییراتِ ظاهری هم از همان "
            "چرخه‌ی Draft/Preview/Publish/Restore عبور کنند، نه یک مسیرِ زنده‌ی جدا."
        ),
    )

    content_fingerprint = models.CharField(
        "اثر انگشت محتوا", max_length=64, blank=True,
        help_text="هش SHA-256 محتوای سریالایز‌شده — برای تشخیص drift.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ایجادکننده",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)

    class Meta:
        verbose_name = "نسخه چیدمان"
        verbose_name_plural = "نسخه‌های چیدمان"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["layout", "version_number"],
                name="storefront_layout_version_unique_number_per_layout",
            ),
        ]

    def __str__(self):
        return f"نسخه {self.version_number} — {self.get_status_display()}"

    def effective_header_config(self) -> dict:
        """پیکربندی هدر با پیش‌فرض‌های کامل — کلید ذخیره‌نشده True است، کلید
        صریحاً ``False`` همان ``False`` باقی می‌ماند (بر خلاف فیلتر
        Django ``|default:True`` که مقدار صریح False را هم falsy می‌گیرد)."""
        return {**HEADER_CONFIG_DEFAULTS, **(self.header_config or {})}

    def effective_footer_config(self) -> dict:
        return {**FOOTER_CONFIG_DEFAULTS, **(self.footer_config or {})}

    def effective_appearance_config(self) -> dict:
        """پیکربندیِ ظاهر با پیش‌فرض‌هایِ کامل — همان الگویِ
        ``effective_header_config``. کلیدِ ``color_overrides`` عمداً به
        شکلِ shallow merge نمی‌شود (یک دیکشنریِ تودرتو است) — اگر مقداری
        ذخیره شده باشد، دقیقاً همان مقدار استفاده می‌شود؛ حل‌کردنِ نهاییِ
        رنگ‌ها (پالت پایه + override) وظیفه‌ی ``appearance_service`` است،
        نه این متد (که فقط defaults را کامل می‌کند، دقیقاً مثلِ
        header/footer)."""
        return {**APPEARANCE_CONFIG_DEFAULTS, **(self.appearance_config or {})}

    def compute_fingerprint(self) -> str:
        """هش SHA-256 قطعی از هدر/فوتر/ظاهر/بخش‌ها — مستقل از ترتیب ذخیره‌سازی ردیف‌ها."""
        sections = [
            {"section_key": s.section_key, "order": s.order, "is_active": s.is_active, "settings": s.settings}
            for s in self.sections.order_by("order", "id")
        ]
        payload = {
            "header_config": self.header_config,
            "footer_config": self.footer_config,
            "appearance_config": self.appearance_config,
            "sections": sections,
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class StorefrontSection(TimeStampedModel):
    """یک بخش صفحه اصلی درون یک نسخه چیدمان — نوع، ترتیب، وضعیت، تنظیمات JSON.

    ``section_key`` در برابر Section Registry اعتبارسنجی می‌شود (سرویس،
    نه اینجا) — همان الگویی که مانع بارگذاری template دلخواه یا ارجاع
    نامعتبر می‌شود (بخش ۱۲ گزارش ممیزی).
    """

    version = models.ForeignKey(
        StorefrontLayoutVersion, verbose_name="نسخه چیدمان",
        on_delete=models.CASCADE, related_name="sections",
    )
    section_key = models.CharField("نوع بخش", max_length=50)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)
    settings = models.JSONField("تنظیمات", default=dict, blank=True)
    collapsed_in_editor = models.BooleanField(
        "جمع‌شده در ادیتور", default=False,
        help_text=(
            "فقط نمایش فشرده/باز کارت این بخش داخل سازنده بصری را کنترل می‌کند — "
            "مستقل از is_active؛ هیچ اثری روی نمایش عمومی Storefront ندارد."
        ),
    )
    stable_id = models.UUIDField(
        "شناسه منطقی پایدار", default=uuid.uuid4, editable=False, db_index=True,
        help_text=(
            "هویتِ منطقیِ این بخش که مستقل از PK پایگاه‌داده است — طیِ کلونِ "
            "نسخه (Published → Draft جدید، Restore) دقیقاً همان مقدار حفظ "
            "می‌شود (چون همان بخشِ منطقی است، فقط در نسخه‌ی دیگری). طیِ "
            "تکرار (Duplicate) عمداً یک UUID تازه می‌گیرد (چون یک بخشِ "
            "منطقیِ *جدید* است). این فیلد اجازه می‌دهد ردیف‌های رسانه‌ی "
            "مقیّد به section (HeroSlide/PromotionalBanner/StoryRailItem) "
            "طیِ کلون بتوانند section مقابلِ خودشان را در نسخه‌ی جدید پیدا "
            "کنند — بدون اینکه هرگز به PKِ بخشِ منتشرشده دست بزنند "
            "(Phase 0.5 — نگاه کنید به layout_service._clone_version_content)."
        ),
    )

    class Meta:
        verbose_name = "بخش صفحه فروشگاه"
        verbose_name_plural = "بخش‌های صفحه فروشگاه"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "stable_id"],
                name="storefront_section_unique_stable_id_per_version",
            ),
        ]

    def __str__(self):
        return f"{self.section_key} (#{self.order})"
