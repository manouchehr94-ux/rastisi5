"""دستور idempotent برای ساختِ یک فروشگاهِ QA/Demo کاملاً جدا (پوشاک) —
«فروشگاه لباس تستی راستی سی» — برایِ آزمونِ بصری/تعاملیِ شش Familyِ جدید
(atlas_catalog، ava_fashion، toranj_gifting، sarv_stock، sepidar_handmade،
zarrin_jewelry) رویِ یک مجموعه‌دادهٔ واقعیِ یکسان.

فقط برایِ محیطِ توسعه: در ``DEBUG=False`` اجرا نمی‌شود (این دستور دادهٔ
تستیِ فراوان می‌سازد و هرگز نباید در یک دیتابیسِ Production اجرا شود).

Idempotent: اجرایِ دوباره رکوردِ تکراری نمی‌سازد — همه‌جا از
``get_or_create``/``update_or_create`` رویِ فیلدِ یکتا (معمولاً ``slug``
درونِ همینِ Store) استفاده می‌شود.

Tenant-scoped: این دستور فقط رکوردهایِ متعلق به همینِ Storeِ QA (یا
User/StoreMembership مرتبط) می‌سازد/می‌خواند — هرگز به Storeِ دیگری
(``akhlaghi`` یا هر Storeِ دیگری که مالک روی همان دیتابیس دارد) دست
نمی‌زند. ``--reset`` هم فقط همینِ Storeِ QA را حذف/بازسازی می‌کند؛
هیچ‌وقت Storeِ دیگری را حذف نمی‌کند.

استفاده:
    python manage.py seed_rastisi_fashion_demo --owner-username <کاربرِ موجود>
    python manage.py seed_rastisi_fashion_demo --owner-username <کاربرِ موجود> --reset
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.catalog.models import (
    Brand,
    Category,
    MerchantCollection,
    MerchantCollectionItem,
    Product,
    Vendor,
)
from apps.catalog.services.product_image_service import add_product_image, set_image_variant
from apps.catalog.services.variant_service import create_variant
from apps.content.models import (
    ContentPage,
    DestinationType,
    FooterSettings,
    HeroSlide,
    Menu,
    MenuItem,
    PromotionalBanner,
    StoryRailItem,
)
from apps.core.models import ShopSettings
from apps.storefront_builder import family_registry
from apps.storefront_builder.services import bootstrap_service, layout_service
from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

# --------------------------------------------------------------- شناسهٔ فروشگاه

STORE_SLUG = "rastisi-fashion-test"
STORE_NAME = "فروشگاه لباس تستی راستی سی"
STORE_ADMIN_SUBDOMAIN = "rastisi-fashion-test"

STORE_CONTACT = {
    "tagline": "پوشاکِ روزمره — دادهٔ QA/آزمونی",
    "description": (
        "این فروشگاه صرفاً یک مجموعه‌دادهٔ آزمایشیِ محلی برایِ آزمونِ بصریِ "
        "شش Familyِ جدیدِ Storefront Builder است — هیچ داده‌ای در این فروشگاه "
        "واقعی نیست."
    ),
    "contact_phone": "09123456789",
    "contact_email": "test-fashion@example.com",
    "contact_address": "تهران، خیابان تست راستی سی، پلاک ۱۲۳، واحد ۴",
}
STORE_TELEPHONE = "02112345678"
STORE_POSTAL_CODE = "1234512345"
STORE_SUPPORT_HOURS = "شنبه تا چهارشنبه ۹ تا ۱۸ / پنجشنبه ۹ تا ۱۴"

GIFT_WRAP_PRICE = Decimal("25000")

# --------------------------------------------------------------- دسته‌بندی‌ها

PRIMARY_CATEGORIES = [
    {"name": "تی‌شرت و تاپ", "slug": "tshirt-top", "icon": "👕", "children": [
        {"name": "تی‌شرت مردانه", "slug": "tshirt-men"},
        {"name": "تاپ زنانه", "slug": "top-women"},
    ]},
    {"name": "پیراهن", "slug": "shirt", "icon": "👔", "children": [
        {"name": "پیراهن رسمی", "slug": "shirt-formal"},
        {"name": "پیراهن کژوال", "slug": "shirt-casual"},
    ]},
    {"name": "شلوار و جین", "slug": "pants-jeans", "icon": "👖", "children": [
        {"name": "شلوار جین", "slug": "jeans"},
        {"name": "شلوار کتان", "slug": "pants-chino"},
    ]},
    {"name": "مانتو و رویه", "slug": "manto-overlay", "icon": "🧥", "children": [
        {"name": "مانتو مجلسی", "slug": "manto-formal"},
        {"name": "رویه کژوال", "slug": "overlay-casual"},
    ]},
    {"name": "کت و کاپشن", "slug": "coat-jacket", "icon": "🧥", "children": [
        {"name": "کت رسمی", "slug": "coat-formal"},
        {"name": "کاپشن زمستانی", "slug": "jacket-winter"},
    ]},
    {"name": "هودی و سویشرت", "slug": "hoodie-sweatshirt", "icon": "🧶", "children": [
        {"name": "هودی کلاه‌دار", "slug": "hoodie-hooded"},
        {"name": "سویشرت یقه‌گرد", "slug": "sweatshirt-crew"},
    ]},
    {"name": "لباس ورزشی", "slug": "sportswear", "icon": "🏃", "children": [
        {"name": "شلوار ورزشی", "slug": "sport-pants"},
        {"name": "تیشرت ورزشی", "slug": "sport-tshirt"},
    ]},
    {"name": "کفش", "slug": "shoes", "icon": "👟", "children": [
        {"name": "کفش روزمره", "slug": "shoes-casual"},
        {"name": "کفش ورزشی", "slug": "shoes-sport"},
    ]},
    {"name": "کیف", "slug": "bag", "icon": "👜", "children": [
        {"name": "کیف دوشی", "slug": "bag-shoulder"},
        {"name": "کیف دستی", "slug": "bag-handbag"},
    ]},
    {"name": "اکسسوری", "slug": "accessory", "icon": "🧣", "children": [
        {"name": "شال و روسری", "slug": "accessory-scarf"},
        {"name": "کمربند و کلاه", "slug": "accessory-belt-hat"},
    ]},
]

BRANDS = [
    {"name": "آریا استایل", "slug": "aria-style"},
    {"name": "ویرا پوش", "slug": "vira-poosh"},
    {"name": "ماهان مد", "slug": "mahan-mode"},
    {"name": "رایان کژوال", "slug": "rayan-casual"},
]

VENDOR = {"name": "فروشندهٔ QA راستی سی", "slug": "rastisi-fashion-vendor"}

COLLECTIONS = [
    {"name": "پرفروش‌های راستی سی", "slug": "bestsellers-rastisi"},
    {"name": "تازه رسیده‌ها", "slug": "new-arrivals-rastisi"},
    {"name": "تخفیف ویژه", "slug": "special-discount-rastisi"},
    {"name": "استایل روزمره", "slug": "everyday-style-rastisi"},
    {"name": "انتخاب تابستانی", "slug": "summer-pick-rastisi"},
    {"name": "پیشنهاد راستی سی", "slug": "rastisi-recommends"},
]

SIZES = ["S", "M", "L", "XL"]
COLORS = [
    ("مشکی", "#1F2937"),
    ("سفید", "#F9FAFB"),
    ("سرمه‌ای", "#1E3A8A"),
    ("کرم", "#F5E9D6"),
    ("سبز", "#166534"),
    ("آبی", "#2563EB"),
    ("قرمز", "#DC2626"),
]

NAME_PATTERNS = {
    "tshirt-men": "تی‌شرت نخی مردانه مدل {name}",
    "top-women": "تاپ زنانه مدل {name}",
    "shirt-formal": "پیراهن رسمی مدل {name}",
    "shirt-casual": "پیراهن کژوال مدل {name}",
    "jeans": "شلوار جین مدل {name}",
    "pants-chino": "شلوار کتان مدل {name}",
    "manto-formal": "مانتو مجلسی مدل {name}",
    "overlay-casual": "رویهٔ کژوال مدل {name}",
    "coat-formal": "کت رسمی مدل {name}",
    "jacket-winter": "کاپشن زمستانی مدل {name}",
    "hoodie-hooded": "هودی کلاه‌دار مدل {name}",
    "sweatshirt-crew": "سویشرت یقه‌گرد مدل {name}",
    "sport-pants": "شلوار ورزشی مدل {name}",
    "sport-tshirt": "تیشرت ورزشی مدل {name}",
    "shoes-casual": "کفش روزمره مدل {name}",
    "shoes-sport": "کفش ورزشی مدل {name}",
    "bag-shoulder": "کیف دوشی مدل {name}",
    "bag-handbag": "کیف دستی مدل {name}",
    "accessory-scarf": "شال و روسری مدل {name}",
    "accessory-belt-hat": "کمربند و کلاه مدل {name}",
}

FIRST_NAMES = [
    "آریا", "ویرا", "ماهان", "آوا", "رایان", "هانا", "سارینا", "کیانا", "آرمین",
    "دنیز", "پارمیس", "رها", "آرتین", "ستایش", "بردیا", "نیکا", "سام", "یاسمین",
    "پرهام", "الینا",
]

CONTENT_PAGES = [
    {"title": "درباره ما", "slug": "about-us", "footer_column": ContentPage.FooterColumn.QUICK_ACCESS,
     "body": "فروشگاه لباس تستی راستی سی — یک مجموعه‌دادهٔ QA برایِ آزمونِ بصریِ Storefront Builder."},
    {"title": "تماس با ما", "slug": "contact-us", "footer_column": ContentPage.FooterColumn.QUICK_ACCESS,
     "body": f"تلفن: {STORE_TELEPHONE} — ایمیل: {STORE_CONTACT['contact_email']}"},
    {"title": "روش‌های ارسال", "slug": "shipping-methods", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ روش‌های ارسال است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
    {"title": "شرایط مرجوعی", "slug": "return-policy", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ شرایطِ مرجوعی است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
    {"title": "راهنمای خرید", "slug": "shopping-guide", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ راهنمایِ خرید است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
    {"title": "حریم خصوصی", "slug": "privacy-policy", "footer_column": ContentPage.FooterColumn.CUSTOMER_SERVICE,
     "body": "این یک متنِ آزمایشیِ حریمِ خصوصی است — صرفاً برایِ آزمونِ فروشگاهِ QA."},
]

DEFAULT_FAMILY_SLUG = "atlas_catalog"


def _text_font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _generate_image_bytes(*, width: int, height: int, bg_hex: str, label: str) -> bytes:
    """یک تصویرِ Portrait ساختگیِ برندنشان‌دار (فقط یک هندسه‌ی ساده + متن)
    را در حافظه می‌سازد — هرگز دانلود/کپیِ تصویرِ سایتِ ثالث نیست."""
    image = Image.new("RGB", (width, height), bg_hex)
    draw = ImageDraw.Draw(image)
    # هندسه‌ی ساده‌ی شبیه‌به‌پوشاک — یک ذوزنقه/بیضی به‌جایِ عکسِ واقعی.
    inset_x = int(width * 0.18)
    top = int(height * 0.18)
    bottom = int(height * 0.82)
    lighten = tuple(min(255, c + 40) for c in Image.new("RGB", (1, 1), bg_hex).getpixel((0, 0)))
    draw.rounded_rectangle((inset_x, top, width - inset_x, bottom), radius=24, fill=lighten)
    draw.ellipse((width * 0.35, top - 30, width * 0.65, top + 30), fill=lighten)
    font = _text_font(28)
    text = label[:28]
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        text_w, text_h = draw.textsize(text, font=font)
    draw.text(((width - text_w) / 2, height - text_h - 24), text, fill="#111111", font=font)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _uploaded_image(*, filename: str, width: int, height: int, bg_hex: str, label: str) -> SimpleUploadedFile:
    data = _generate_image_bytes(width=width, height=height, bg_hex=bg_hex, label=label)
    return SimpleUploadedFile(filename, data, content_type="image/jpeg")


class Command(BaseCommand):
    help = (
        "می‌سازد/بازمی‌سازد یک فروشگاهِ QA/Demo کاملاً جدا (پوشاک، «فروشگاه لباس "
        "تستی راستی سی») برایِ آزمونِ بصریِ شش Familyِ جدیدِ Storefront Builder. "
        "Idempotent، Tenant-scoped، فقط در DEBUG اجرا می‌شود."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-username", required=True,
            help="یوزرنیمِ یک کاربرِ از‌قبل‌موجود که مالکِ StoreMembership این فروشگاهِ QA خواهد شد.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help=(
                "پیش از ساختنِ دوباره، این Storeِ QA (فقط با اسلاگِ "
                f"«{STORE_SLUG}») را کاملاً حذف می‌کند — هرگز Storeِ دیگری را لمس نمی‌کند."
            ),
        )
        parser.add_argument(
            "--family", default=DEFAULT_FAMILY_SLUG,
            help=f"اسلاگِ Familyی که در پایان منتشر می‌شود (پیش‌فرض: {DEFAULT_FAMILY_SLUG}).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "این دستور فقط در DEBUG=True قابل‌اجراست — یک دیتابیسِ Production هرگز "
                "نباید دادهٔ QA/Demo دریافت کند."
            )

        owner_username = options["owner_username"]
        try:
            owner = User.objects.get(username=owner_username)
        except User.DoesNotExist as exc:
            raise CommandError(
                f"کاربری با یوزرنیمِ «{owner_username}» یافت نشد. این دستور هرگز یک کاربرِ "
                "ناامنِ پیش‌فرض نمی‌سازد — ابتدا کاربر را با «python manage.py createsuperuser» "
                "یا مسیرِ ثبت‌نامِ عادیِ فروشگاه بسازید، سپس دوباره اجرا کنید."
            ) from exc

        family_slug = options["family"]
        family = family_registry.get_family(family_slug)
        if family is None:
            valid = ", ".join(sorted(family_registry.FAMILY_REGISTRY.keys()))
            raise CommandError(f"Familyِ «{family_slug}» در Registry ثبت نشده. Familyهایِ معتبر: {valid}")

        if options["reset"]:
            self._reset(owner_username)

        with transaction.atomic():
            store = self._seed_store()
            self._seed_domain(store)
            self._seed_membership(store, owner)
            self._seed_shop_settings(store)
            self._seed_footer_settings(store)
            vendor = self._seed_vendor(store)
            categories = self._seed_categories(store)
            brands = self._seed_brands(store)
            products = self._seed_products(store, vendor, categories, brands)
            variant_stats = self._seed_variants(products)
            image_stats = self._seed_product_images(products)
            collections = self._seed_collections(store, products)
            hero_count = self._seed_hero_slides(store)
            banner_count = self._seed_banners(store)
            story_count = self._seed_story_rail(store, categories, products, collections)
            menu_item_count = self._seed_navigation(store, categories, collections)
            content_page_count = self._seed_content_pages(store)
            self._seed_builder(store, owner, family)

        self.stdout.write(self.style.SUCCESS(
            "seed_rastisi_fashion_demo با موفقیت اجرا شد:\n"
            f"  Store: {store.slug} (admin_subdomain={store.admin_subdomain})\n"
            f"  دسته‌بندی: {Category.objects.filter(store=store).count()}\n"
            f"  برند: {Brand.objects.filter(store=store).count()}\n"
            f"  کالا: {Product.objects.filter(store=store).count()}\n"
            f"  تنوع: {variant_stats['total']} (روی {variant_stats['products_with_variants']} کالا؛ "
            f"{variant_stats['image_mapped']} تنوعِ تصویرمحور)\n"
            f"  تصویرِ کالا: {image_stats}\n"
            f"  کالکشن: {len(collections)}\n"
            f"  اسلایدِ هیرو: {hero_count}\n"
            f"  بنر تبلیغاتی: {banner_count}\n"
            f"  آیتمِ استوری: {story_count}\n"
            f"  آیتمِ منو: {menu_item_count}\n"
            f"  صفحهٔ محتوایی: {content_page_count}\n"
            f"  Familyِ منتشرشده: {family.slug}\n"
            "  ویدیویِ کالا: SKIPPED — نیازمندِ یک لینکِ خارجیِ واقعیِ یوتیوب/آپارات/"
            "اینستاگرام است (apps.catalog.models.ProductVideo.url)؛ هیچ گزینهٔ محلیِ "
            "کپی‌رایت-ایمن برایِ این مدل وجود ندارد، پس عمداً seed نشد."
        ))

    # ------------------------------------------------------------------ Reset

    @transaction.atomic
    def _reset(self, owner_username):
        """فقط Storeِ QA با همینِ اسلاگِ ثابت را حذف می‌کند — cascade مدلِ
        Django (``on_delete=CASCADE`` رویِ ``store`` در همه‌ی مدل‌هایِ
        Store-owned) بقیه‌ی رکوردهایِ همینِ Store را خودکار پاک می‌کند.
        هرگز Storeِ دیگری (حتی اگر همان owner عضوش باشد) را لمس نمی‌کند.
        اتمیک: اگر حذف در میانه شکست بخورد، هیچ‌چیزی نصفه‌کاره حذف نمی‌شود."""
        existing = Store.objects.filter(slug=STORE_SLUG).first()
        if existing is None:
            self.stdout.write("  --reset: Storeِ QA از قبل وجود نداشت — چیزی حذف نشد.")
            return
        self.stdout.write(f"  --reset: حذفِ کاملِ Storeِ QA «{existing.slug}» (pk={existing.pk})…")
        existing.delete()

    # ------------------------------------------------------------------ Store/Domain/Membership

    def _seed_store(self) -> Store:
        store, created = Store.objects.get_or_create(
            slug=STORE_SLUG,
            defaults={
                "name": STORE_NAME,
                "admin_subdomain": normalize_admin_subdomain(STORE_ADMIN_SUBDOMAIN),
                "status": Store.Status.ACTIVE,
                "onboarding_stage": Store.OnboardingStage.DONE,
                "onboarding_completed_at": timezone.now(),
            },
        )
        if not created and store.name != STORE_NAME:
            store.name = STORE_NAME
            store.status = Store.Status.ACTIVE
            store.save(update_fields=["name", "status", "updated_at"])
        self._log("Store", 1 if created else 0)
        return store

    def _seed_domain(self, store: Store) -> None:
        """میزبانِ عمومیِ توسعه — ``<admin_subdomain>.rastisi.localhost`` در
        DEBUG (``settings.RASTISI_ADMIN_DOMAIN_SUFFIX``) — با
        ``verification_status=VERIFIED``/``verified_at`` مقداردهی‌شده تا
        ``domain_is_eligible_for_routing`` واقعاً صادقانه اجازهٔ رندرِ
        عمومی/Publicِ فروشگاه را بدهد (نگاه کنید به
        ``apps.stores.resolution``)."""
        hostname = f"{store.admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        domain, created = StoreDomain.objects.get_or_create(
            store=store, hostname=hostname,
            defaults={
                "is_primary": True,
                "domain_type": StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                "verification_status": StoreDomain.VerificationStatus.VERIFIED,
                "verified_at": timezone.now(),
            },
        )
        if not created and domain.verification_status != StoreDomain.VerificationStatus.VERIFIED:
            domain.verification_status = StoreDomain.VerificationStatus.VERIFIED
            domain.verified_at = timezone.now()
            domain.is_primary = True
            domain.save(update_fields=["verification_status", "verified_at", "is_primary", "updated_at"])
        self._log("StoreDomain", 1 if created else 0)

    def _seed_membership(self, store: Store, owner) -> None:
        membership, created = StoreMembership.objects.get_or_create(
            store=store, user=owner,
            defaults={
                "role": StoreMembership.Role.OWNER,
                "status": StoreMembership.MembershipStatus.ACTIVE,
                "accepted_at": timezone.now(),
            },
        )
        if not created and membership.status != StoreMembership.MembershipStatus.ACTIVE:
            membership.role = StoreMembership.Role.OWNER
            membership.status = StoreMembership.MembershipStatus.ACTIVE
            membership.accepted_at = membership.accepted_at or timezone.now()
            membership.save(update_fields=["role", "status", "accepted_at", "updated_at"])
        self._log("StoreMembership", 1 if created else 0)

    def _seed_shop_settings(self, store: Store) -> None:
        shop = ShopSettings.provision_for(store)
        shop.name = STORE_NAME
        shop.tagline = STORE_CONTACT["tagline"]
        shop.description = STORE_CONTACT["description"]
        shop.contact_phone = STORE_CONTACT["contact_phone"]
        shop.contact_email = STORE_CONTACT["contact_email"]
        shop.contact_address = STORE_CONTACT["contact_address"]
        # کادوپیچی (Toranj) — فعال با یک قیمتِ نمونهٔ منطقی (تومان).
        shop.gift_wrap_available = True
        shop.gift_wrap_price = GIFT_WRAP_PRICE
        shop.save()
        self._log("ShopSettings", 0, note="provision + به‌روزرسانیِ هویت/کادوپیچی")

    def _seed_footer_settings(self, store: Store) -> None:
        footer = FooterSettings.provision_for(store)
        footer.is_enabled = True
        footer.show_branding = True
        footer.description = STORE_CONTACT["description"]
        footer.show_contact = True
        footer.address = STORE_CONTACT["contact_address"]
        footer.phone = STORE_TELEPHONE
        footer.email = STORE_CONTACT["contact_email"]
        footer.working_hours = STORE_SUPPORT_HOURS
        footer.show_navigation = True
        footer.show_social_links = False
        footer.copyright_text = "© فروشگاه لباس تستی راستی سی — دادهٔ QA"
        footer.save()
        self._log("FooterSettings", 0, note="provision + به‌روزرسانیِ هویت")

    # ------------------------------------------------------------------ Vendor/Category/Brand

    def _seed_vendor(self, store: Store) -> Vendor:
        vendor, created = Vendor.objects.get_or_create(
            store=store, slug=VENDOR["slug"], defaults={"name": VENDOR["name"], "is_active": True},
        )
        self._log("Vendor", 1 if created else 0)
        return vendor

    def _seed_categories(self, store: Store) -> dict:
        by_slug = {}
        created_count = 0
        for order, top in enumerate(PRIMARY_CATEGORIES):
            parent, created = Category.objects.get_or_create(
                store=store, slug=top["slug"],
                defaults={"name": top["name"], "icon": top["icon"], "order": order, "is_active": True},
            )
            created_count += int(created)
            by_slug[top["slug"]] = parent
            for child_order, child in enumerate(top.get("children", [])):
                child_obj, child_created = Category.objects.get_or_create(
                    store=store, slug=child["slug"],
                    defaults={"name": child["name"], "parent": parent, "order": child_order, "is_active": True},
                )
                created_count += int(child_created)
                by_slug[child["slug"]] = child_obj
        self._log("Category", created_count)
        return by_slug

    def _seed_brands(self, store: Store) -> dict:
        by_slug = {}
        created_count = 0
        for data in BRANDS:
            brand, created = Brand.objects.get_or_create(
                store=store, slug=data["slug"], defaults={"name": data["name"], "is_active": True},
            )
            created_count += int(created)
            by_slug[data["slug"]] = brand
        self._log("Brand", created_count)
        return by_slug

    # ------------------------------------------------------------------ Products

    def _seed_products(self, store: Store, vendor: Vendor, categories: dict, brands: dict) -> list:
        """دقیقاً ۱۰۰ کالا — ۱۰ به‌ازایِ هر یک از ۱۰ دستهٔ اصلی. توزیعِ
        قیمت/موجودی/وضعیت طبقِ الزامِ صریحِ کار: ~۷۵ موجودیِ نرمال، ~۱۵
        موجودیِ کم، ~۱۰ کاملاً ناموجود؛ اکثریتِ فعال، تعدادِ اندکی پیش‌نویس/
        غیرفعال برایِ تستِ صحیحِ فیلترِ نمایشِ عمومی."""
        products = []
        brand_slugs = list(brands.keys())
        sku_counter = 1
        product_index = 0
        created_count = 0

        for primary in PRIMARY_CATEGORIES:
            child_slugs = [c["slug"] for c in primary.get("children", [])]
            for i in range(10):
                child_slug = child_slugs[i % len(child_slugs)] if child_slugs else primary["slug"]
                category = categories[child_slug]
                pattern = NAME_PATTERNS.get(child_slug, "{name} — کالایِ تستی")
                first_name = FIRST_NAMES[product_index % len(FIRST_NAMES)]
                name = pattern.format(name=first_name)
                slug = f"{child_slug}-{first_name.lower()}-{i}".replace(" ", "-")
                sku = f"RFT-{sku_counter:04d}"
                sku_counter += 1

                # --- توزیعِ قیمت: کم/متوسط/زیاد + برخی تخفیف‌دار ---
                price_bucket = product_index % 3
                base_price = [Decimal("350000"), Decimal("890000"), Decimal("1850000")][price_bucket]
                price = base_price + Decimal(product_index % 5) * Decimal("15000")
                discount_percent = [0, 0, 15, 20, 30][product_index % 5]

                # --- توزیعِ موجودی: ~۷۵ نرمال / ~۱۵ کم / ~۱۰ صفر (از رویِ ۱۰۰) ---
                stock_bucket = product_index % 20
                if stock_bucket < 15:
                    stock = 20 + (product_index % 30)
                elif stock_bucket < 18:
                    stock = 1 + (product_index % 3)
                else:
                    stock = 0

                # --- توزیعِ وضعیت: اکثریتِ فعال، تعدادِ اندکِ Draft/Inactive ---
                if product_index % 33 == 0:
                    status = Product.Status.DRAFT
                elif product_index % 37 == 0:
                    status = Product.Status.INACTIVE
                else:
                    status = Product.Status.ACTIVE

                brand = brands[brand_slugs[product_index % len(brand_slugs)]] if brand_slugs else None

                product, created = Product.objects.get_or_create(
                    store=store, sku=sku,
                    defaults={
                        "vendor": vendor, "category": category, "brand": brand,
                        "name": name, "slug": slug,
                        "description": f"{name} — کالایِ آزمایشیِ QA برایِ آزمونِ بصریِ Storefront Builder.",
                        "price": price, "discount_percent": discount_percent, "stock": stock,
                        "status": status, "unit": Product.Unit.PIECE,
                    },
                )
                created_count += int(created)
                products.append(product)
                product_index += 1

        self._log("Product", created_count)
        return products

    # ------------------------------------------------------------------ Variants

    def _seed_variants(self, products: list) -> dict:
        """توزیعِ واریانت طبقِ الزامِ صریحِ کار: بدونِ‌تنوع/فقط‌سایز/فقط‌رنگ/
        رنگ+سایز — حداقل ۳۰ کالایِ چندتنوعی، حداقل ۱۰ کالا با یک تنوعِ
        ناموجود در کنارِ بقیهٔ تنوع‌هایِ موجود، حداقل ۲۰ کالایِ تصویرمحور
        (که ``set_image_variant`` را واقعاً استفاده می‌کنند).

        ``variant_pattern = index % 5`` روی ۱۰۰ کالا دقیقاً ۲۰ تکرارِ هرکدام
        از ۰ تا ۴ می‌سازد:
          * ۰ و ۴ → بدونِ تنوع (۴۰ کالا)؛
          * ۱ → فقط سایز (۲۰ کالا)؛
          * ۲ → فقط رنگ + تصویرمحور (۲۰ کالا — دقیقاً الزامِ «حداقلِ ۲۰»)؛
          * ۳ → رنگ + سایز (۲۰ کالا).
        جمعِ کالاهایِ چندتنوعی = ۶۰ (پترنِ ۱/۲/۳)، بیشتر از الزامِ «حداقل ۳۰».
        """
        total = 0
        products_with_variants = 0
        image_mapped = 0
        zero_stock_alongside_available = 0

        for index, product in enumerate(products):
            variant_pattern = index % 5
            created_any = False

            if variant_pattern in (0, 4):
                # بدونِ تنوع — عمداً دست‌نخورده می‌ماند.
                continue

            # Idempotency: اگر این کالا از اجرایِ قبلی از قبل تنوع دارد، دوباره
            # ساخته نمی‌شود (create_variant رویِ مقدارِ فعالِ تکراری خطا
            # می‌دهد) — فقط در شمارشِ خلاصهٔ پایانی لحاظ می‌شود.
            existing_variants = list(product.variants.all())
            if existing_variants:
                total += len(existing_variants)
                mapped_here = product.images.filter(variant__isnull=False).count()
                image_mapped += mapped_here
                if any(v.stock == 0 for v in existing_variants) and any(v.stock > 0 for v in existing_variants):
                    zero_stock_alongside_available += 1
                products_with_variants += 1
                continue

            # هر دومینِ کالایِ چندتنوعی (index % 2 == 0)، تنوعِ اولش را عمداً
            # ناموجود می‌کند تا بقیهٔ تنوع‌ها همچنان موجود بمانند — این یکی
            # از راه‌هایِ رسیدن به الزامِ «حداقل ۱۰ کالا با یک تنوعِ ناموجود
            # در کنارِ بقیهٔ تنوع‌هایِ موجود» است (پترنِ ۱/۲/۳ جمعاً ۶۰ کالا،
            # نیمی از آن‌ها = ۳۰ کالا، خیلی بیشتر از حداقلِ ۱۰).
            first_variant_out_of_stock = index % 2 == 0

            if variant_pattern in (1, 3):
                # فقط سایز (یا سایز به‌همراهِ رنگِ زیر برایِ pattern==3).
                for size_index, size in enumerate(SIZES):
                    if first_variant_out_of_stock and size_index == 0:
                        size_stock = 0
                    else:
                        size_stock = 5 + size_index
                    create_variant(
                        product, attribute="سایز", value=size, stock=size_stock,
                        is_active=True,
                    )
                    total += 1
                created_any = True

            if variant_pattern in (2, 3):
                # فقط رنگ (یا رنگ اضافه‌شده به سایزِ بالا برایِ pattern==3 → رنگ+سایز).
                colors_for_product = COLORS[index % len(COLORS):] + COLORS[: index % len(COLORS)]
                colors_for_product = colors_for_product[:3] or COLORS[:3]
                # فقط pattern==2 (دقیقاً ۲۰ کالا از ۱۰۰) تصویرِ اختصاصیِ رنگ
                # می‌گیرد — الزامِ «حداقل ۲۰ کالایِ تصویرمحور» را دقیقاً برآورده می‌کند.
                should_map_image = variant_pattern == 2
                for color_index, (color_name, color_hex) in enumerate(colors_for_product):
                    if first_variant_out_of_stock and color_index == 0 and variant_pattern == 2:
                        # برایِ pattern==3، ناموجودسازیِ اولین‌تنوع از طریقِ سایز
                        # (بالا) کافی است — این‌جا فقط برایِ pattern==2 (که سایز
                        # ندارد) دوباره اعمال می‌شود تا آن گروه هم پوشش داده شود.
                        color_stock = 0
                    else:
                        color_stock = 4 + color_index * 2
                    variant = create_variant(
                        product, attribute="رنگ", value=color_name, value_hex=color_hex,
                        stock=color_stock, is_active=True,
                    )
                    total += 1
                    if should_map_image:
                        image = add_product_image(
                            product,
                            _uploaded_image(
                                filename=f"{product.slug}-{color_name}.jpg",
                                width=600, height=750, bg_hex=color_hex, label=f"{product.name} — {color_name}",
                            ),
                            alt=f"{product.name} — رنگ {color_name}",
                        )
                        set_image_variant(image, variant)
                        image_mapped += 1
                created_any = True

            if created_any:
                products_with_variants += 1
                if first_variant_out_of_stock:
                    zero_stock_alongside_available += 1
                product.product_type = Product.ProductType.VARIABLE
                product.save(update_fields=["product_type"])

        return {
            "total": total, "products_with_variants": products_with_variants,
            "image_mapped": image_mapped, "zero_stock_alongside_available": zero_stock_alongside_available,
        }

    # ------------------------------------------------------------------ Images

    def _seed_product_images(self, products: list) -> int:
        """حداقل ۲ تصویرِ عمومی به‌ازایِ هر کالایِ «معمولی» (بدونِ عکسِ
        تنوع‌محورِ قبلاً ساخته‌شده در ``_seed_variants``) — پالتِ رنگی طبقِ
        دستهٔ کالا، idempotent (کالایِ دارایِ تصویر رد می‌شود)."""
        created_count = 0
        category_palette = {}
        for i, primary in enumerate(PRIMARY_CATEGORIES):
            hue_hexes = ["#EDE9FE", "#FEF3C7", "#DCFCE7", "#FEE2E2", "#E0F2FE", "#FDE68A", "#F1F5F9", "#FCE7F3", "#E2E8F0", "#FFF7ED"]
            category_palette[primary["slug"]] = hue_hexes[i % len(hue_hexes)]

        for product in products:
            if product.images.exists():
                continue
            top_slug = product.category.parent.slug if product.category and product.category.parent else (
                product.category.slug if product.category else "misc"
            )
            bg = category_palette.get(top_slug, "#EDE9FE")
            for shot in range(2):
                add_product_image(
                    product,
                    _uploaded_image(
                        filename=f"{product.slug}-{shot}.jpg", width=600, height=750,
                        bg_hex=bg, label=product.name,
                    ),
                    alt=product.name,
                )
            created_count += 2
        return created_count

    # ------------------------------------------------------------------ Collections

    def _seed_collections(self, store: Store, products: list) -> list:
        collections = []
        visible_products = [p for p in products if p.status == Product.Status.ACTIVE]
        chunk_size = max(len(visible_products) // len(COLLECTIONS), 5) if visible_products else 0

        for c_index, data in enumerate(COLLECTIONS):
            collection, created = MerchantCollection.objects.get_or_create(
                store=store, slug=data["slug"], defaults={"name": data["name"], "is_active": True},
            )
            collections.append(collection)
            if not created:
                continue
            start = c_index * chunk_size
            end = start + min(chunk_size, 12)
            members = visible_products[start:end] or visible_products[:8]
            MerchantCollectionItem.objects.bulk_create([
                MerchantCollectionItem(collection=collection, product=product, order=order)
                for order, product in enumerate(members)
            ])
        self._log("MerchantCollection", MerchantCollection.objects.filter(store=store).count())
        return collections

    # ------------------------------------------------------------------ Hero / Banners / Story rail

    def _seed_hero_slides(self, store: Store) -> int:
        titles = [
            ("کالکشن تابستانی راستی سی", "جدیدترین‌های فصل را ببینید"),
            ("استایل روزمره", "لباس‌هایی برای هر روز شما"),
            ("تازه‌های این هفته", "محصولات تازه رسیده"),
            ("پیشنهادهای ویژه", "تخفیف‌های محدود، همین امروز"),
        ]
        created_count = 0
        colors = ["#111827", "#7C2D12", "#0F172A", "#78350F"]
        for order, (title, subtitle) in enumerate(titles):
            if HeroSlide.objects.filter(store=store, title=title).exists():
                continue
            slide = HeroSlide(
                store=store, title=title, subtitle=subtitle, display_order=order, is_active=True,
                show_button=False, destination_type=DestinationType.NONE,
            )
            slide.desktop_image = _uploaded_image(
                filename=f"hero-{order}.jpg", width=1600, height=700, bg_hex=colors[order % len(colors)], label=title,
            )
            slide.save()
            created_count += 1
        self._log("HeroSlide", created_count)
        return created_count

    def _seed_banners(self, store: Store) -> int:
        titles = ["پرفروش‌های تابستان", "جدیدترین کلکسیون", "تخفیف ویژهٔ اعضا", "ارسال رایگان بالای ۵۰۰ هزار تومان"]
        created_count = 0
        colors = ["#334155", "#7C3AED", "#B45309", "#0E7490"]
        for order, title in enumerate(titles):
            if PromotionalBanner.objects.filter(store=store, title=title).exists():
                continue
            banner = PromotionalBanner(
                store=store, title=title, display_order=order, is_active=True,
                show_button=False, destination_type=DestinationType.NONE,
            )
            banner.desktop_image = _uploaded_image(
                filename=f"banner-{order}.jpg", width=1200, height=500, bg_hex=colors[order % len(colors)], label=title,
            )
            banner.save()
            created_count += 1
        self._log("PromotionalBanner", created_count)
        return created_count

    def _seed_story_rail(self, store: Store, categories: dict, products: list, collections: list) -> int:
        """۱۰ آیتمِ استوری با ترکیبی از مقصدِ دسته‌بندی/محصول/کالکشن."""
        primary_categories = [categories[p["slug"]] for p in PRIMARY_CATEGORIES]
        visible_products = [p for p in products if p.status == Product.Status.ACTIVE][:4]
        created_count = 0
        colors = ["#DB2777", "#0891B2", "#CA8A04", "#16A34A", "#4F46E5", "#EA580C", "#0F766E", "#9333EA", "#DC2626", "#334155"]

        story_targets = []
        for category in primary_categories[:5]:
            story_targets.append(("category", category))
        for product in visible_products:
            story_targets.append(("product", product))
        for collection in collections[:1]:
            story_targets.append(("collection", collection))
        while len(story_targets) < 10 and primary_categories:
            story_targets.append(("category", primary_categories[len(story_targets) % len(primary_categories)]))
        story_targets = story_targets[:10]

        for order, (kind, target) in enumerate(story_targets):
            title = getattr(target, "name", "")[:20] or f"استوری {order + 1}"
            if StoryRailItem.objects.filter(store=store, title=title, display_order=order).exists():
                continue
            item = StoryRailItem(store=store, title=title, display_order=order, is_active=True)
            if kind == "category":
                item.destination_type = DestinationType.CATEGORY
                item.destination_category = target
            elif kind == "product":
                item.destination_type = DestinationType.PRODUCT
                item.destination_product = target
            else:
                item.destination_type = DestinationType.COLLECTION
                item.destination_collection = target
            item.image = _uploaded_image(
                filename=f"story-{order}.jpg", width=400, height=400, bg_hex=colors[order % len(colors)], label=title,
            )
            item.save()
            created_count += 1
        self._log("StoryRailItem", created_count)
        return created_count

    # ------------------------------------------------------------------ Navigation

    def _seed_navigation(self, store: Store, categories: dict, collections: list) -> int:
        menu, _ = Menu.objects.get_or_create(
            store=store, location=Menu.Location.HEADER, defaults={"title": "منوی اصلی", "is_active": True},
        )
        created_count = 0
        order = 0
        for primary in PRIMARY_CATEGORIES:
            category = categories[primary["slug"]]
            item, created = MenuItem.objects.get_or_create(
                menu=menu, title=primary["name"], parent=None,
                defaults={
                    "display_order": order, "is_active": True,
                    "destination_type": DestinationType.CATEGORY, "destination_category": category,
                },
            )
            created_count += int(created)
            order += 1

        collection_by_slug = {c.slug: c for c in collections}
        extra_links = [
            ("محصولات جدید", collection_by_slug.get("new-arrivals-rastisi")),
            ("پرفروش‌ها", collection_by_slug.get("bestsellers-rastisi")),
            ("تخفیف‌ها", collection_by_slug.get("special-discount-rastisi")),
        ]
        for title, collection in extra_links:
            if collection is None:
                continue
            item, created = MenuItem.objects.get_or_create(
                menu=menu, title=title, parent=None,
                defaults={
                    "display_order": order, "is_active": True,
                    "destination_type": DestinationType.COLLECTION, "destination_collection": collection,
                },
            )
            created_count += int(created)
            order += 1

        self._log("MenuItem", created_count)
        return created_count

    # ------------------------------------------------------------------ Content pages

    def _seed_content_pages(self, store: Store) -> int:
        created_count = 0
        now = timezone.now()
        for data in CONTENT_PAGES:
            page, created = ContentPage.objects.get_or_create(
                store=store, slug=data["slug"],
                defaults={
                    "title": data["title"], "body": data["body"],
                    "status": ContentPage.Status.PUBLISHED, "published_at": now,
                    "show_in_footer": True, "footer_column": data["footer_column"],
                },
            )
            created_count += int(created)
        self._log("ContentPage", created_count)
        return created_count

    # ------------------------------------------------------------------ Builder lifecycle

    def _seed_builder(self, store: Store, owner, family) -> None:
        """چیدمانِ Builder را دقیقاً از طریقِ همان سرویس‌هایِ Production
        می‌سازد — هرگز StorefrontSection/StorefrontLayoutVersion را دستی
        نمی‌سازد. اولین ``get_or_create_draft`` روی یک Storeِ کاملاً تازه
        خودکار bootstrap عمومی می‌سازد؛ سپس appearance_config با Familyِ
        درخواستی تنظیم و چیدمانِ Sectionِ *واقعیِ* همان Family جایگزین،
        و در پایان منتشر می‌شود — دقیقاً همان مسیرِ کدی که
        ``storefront_appearance_editor`` (خودِ Builder UI) طی می‌کند."""
        draft = layout_service.get_or_create_draft(store, user=owner)
        cleaned = layout_service.validate_appearance_config({
            "family_slug": family.slug, "preset_slug": family.default_preset_slug,
        })
        draft.appearance_config = cleaned
        draft.save(update_fields=["appearance_config"])
        bootstrap_service.apply_family_default_sections(draft, family)
        layout_service.publish(store, user=owner)
        self._log("StorefrontLayoutVersion", 0, note=f"Draft ساخته و با Family «{family.slug}» منتشر شد")

    # ------------------------------------------------------------------ Logging

    def _log(self, label, created_count, note=""):
        if note:
            self.stdout.write(f"  {label}: {note}")
        else:
            self.stdout.write(f"  {label}: {created_count} رکورد جدید ساخته شد")
