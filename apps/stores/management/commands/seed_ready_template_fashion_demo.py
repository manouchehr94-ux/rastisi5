"""دستورِ idempotent برایِ ساختِ یک فروشگاهِ Demo کاملاً جدا و قطعی (پوشاک) —
«Rasti Mode Demo» — Phase 1 (Deterministic Data Foundation) از کارِ
«Ready Template Demo Fashion Store».

هدف: یک مجموعه‌دادهٔ واقعی/قطعی (نه محتوایِ ساختگیِ Templateمحور) که بعداً
برایِ رندرِ همان storefront از میانِ هر ۸ Ready Template استفاده می‌شود —
این فاز فقط دادهٔ پایه را می‌سازد؛ هیچ پیش‌نمایشِ Gallery/اسکرین‌شاتی اینجا
تولید نمی‌شود (نگاه کنید به دفترچهٔ اجرا برایِ فازهایِ بعدی).

ایزوله/Tenant-scoped: این دستور فقط رکوردهایِ متعلق به همینِ Storeِ ثابتِ
Demo (اسلاگِ ``rasti-mode-demo``) را می‌سازد/می‌خواند — هرگز به هیچ Storeِ
دیگری (نه ``rastisi-fashion-test``، نه ``akhlaghi``، نه هیچ Storeِ واقعیِ
مرچنت) دست نمی‌زند؛ نه دادهٔ آن‌ها را می‌خواند، نه کپی می‌کند. ``--reset``
هم فقط همینِ اسلاگِ ثابت را حذف می‌کند — هیچ آرگومانی برایِ تغییرِ Store
هدفِ reset وجود ندارد (طراحیِ عمدی: امکانِ حذفِ اشتباهیِ Storeِ دیگر از
پایه وجود ندارد).

Idempotent: اجرایِ دوباره رکوردِ تکراری نمی‌سازد و شمارش‌هایِ دقیقِ کار
(۵۰ کالا، ۱۰ دسته، ۶ برند و...) هرگز رشد نمی‌کنند.

از موتورِ واقعیِ Attribute/Option/Variant (``variant_engine_service`` —
Phase 1D، نه یک شِمایِ اختصاصیِ این دستور) برایِ ترکیب‌هایِ واقعیِ
رنگ×سایز استفاده می‌کند — هر ترکیب یک ``ProductVariant`` واقعی با
``combination_key`` است، نه دو فهرستِ مستقلِ رنگ/سایز.

استفاده:
    python manage.py seed_ready_template_fashion_demo
    python manage.py seed_ready_template_fashion_demo --owner-username <کاربرِ موجود>
    python manage.py seed_ready_template_fashion_demo --reset
"""

from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw

from apps.catalog.models import (
    Brand,
    Category,
    MerchantCollection,
    Product,
    ProductOption,
    ProductVariant,
    Vendor,
)
from apps.catalog.services import collection_service, variant_engine_service
from apps.catalog.services.product_image_service import add_product_image, set_image_option_value
from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

# ------------------------------------------------------------------ شناسهٔ فروشگاه

STORE_SLUG = "rasti-mode-demo"
STORE_NAME = "Rasti Mode Demo"
STORE_ADMIN_SUBDOMAIN = "rasti-mode-demo"

VENDOR = {"name": "Rasti Mode Demo Vendor", "slug": "rasti-mode-demo-vendor"}

# ------------------------------------------------------------------ برندها (دقیقاً ۶، بدونِ لوگویِ خارجی)

BRAND_NAMES = ["Demo Nova", "Demo Mira", "Demo Arden", "Demo Rowe", "Demo Lunar", "Demo Vero"]

# ------------------------------------------------------------------ دسته‌بندی‌ها (دقیقاً ۱۰، مسطح)

CATEGORY_NAMES = [
    "تی‌شرت و پولوشرت",
    "پیراهن و شومیز",
    "شلوار پارچه‌ای",
    "شلوار جین",
    "هودی و سویشرت",
    "کت و ژاکت",
    "پالتو و بارانی",
    "پیراهن و لباس زنانه",
    "دامن",
    "بافت و پلیور",
]

# ------------------------------------------------------------------ کالکشن‌ها (کپیِ خنثیِ فارسی)

COLLECTIONS = [
    {"name": "جدیدترین‌ها", "description": "تازه‌ترین اضافه‌شده‌های فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "پرفروش‌ها", "description": "پرطرفدارترین انتخاب‌های فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "تخفیف‌های منتخب", "description": "کالاهایِ تخفیف‌دارِ منتخبِ فروشگاهِ نمایشیِ Rasti Mode."},
    {"name": "انتخاب فصل", "description": "ترکیبِ پیشنهادیِ فصل در فروشگاهِ نمایشیِ Rasti Mode."},
]

# ------------------------------------------------------------------ نگاشتِ نامِ رنگِ فارسی → Hex تقریبی
# فقط یک تخمینِ بصریِ خنثی برایِ swatch/تصویرِ Placeholder — هیچ برند/محصولِ
# واقعیِ خارجی به این مقادیر وابسته نیست.

COLOR_HEX = {
    "سفید": "#F9FAFB", "ذغالی": "#374151", "زیتونی": "#6B7B3A", "سرمه‌ای": "#1E3A5F",
    "کرم": "#F5EFDC", "آجری": "#B5533C", "سبز خزه‌ای": "#5C6B47", "آبی آسمانی": "#87B8D9",
    "صورتی": "#F4B4C6", "خاکی": "#A38F6D", "عاجی": "#F1E9D8", "مشکی": "#1A1A1A",
    "سنگی": "#A8A296", "موکا": "#6F5847", "بژ": "#D9C7A8", "شیری": "#FAF6EE",
    "ایندیگو": "#3B4B6B", "آبی روشن": "#6FA8D9", "آبی تیره": "#16305C", "آبی سنگشور": "#5E7A9C",
    "گرافیتی": "#3F3F3F", "سبز": "#2F5D3A", "یاسی": "#C9BFE0", "شنی": "#D8C6A0",
    "زرشکی": "#7A1F2B", "طوسی": "#8C8C8C", "تنباکویی": "#8A5A34", "آبی متوسط": "#3E6C9E",
    "خردلی": "#C99A2E", "شتری": "#B08D57", "سبز زمردی": "#045D45", "شامپاینی": "#E9DCC3",
    "جو دوسر": "#C8B78E", "آبی": "#3E6C9E", "آلویی": "#5B3A56", "جین": "#4A6B8A",
}
_FALLBACK_COLOR_HEX = "#9CA3AF"

IN_STOCK = "IN_STOCK"
OUT_OF_STOCK = "OUT_OF_STOCK"
PARTIAL_VARIANT_STOCK = "PARTIAL_VARIANT_STOCK"

_HEALTHY_VARIANT_STOCK = 15
_PARTIAL_HEALTHY_VARIANT_STOCK = 12

# ------------------------------------------------------------------ ماتریسِ کالا (دقیقاً ۵۰ ردیف)
# فرمت: (کد, دستهٔ, نامِ کالا, برند, قیمتِ‌عادی, قیمتِ‌حراج‌یا‌None, [رنگ‌ها], [سایزها], وضعیتِ‌موجودی)

PRODUCT_MATRIX = [
    ("FSH-001", "تی‌شرت و پولوشرت", "تی‌شرت کتان Oversize زنانه", "Demo Nova", 1890000, 1490000, ["سفید", "ذغالی", "زیتونی"], ["XS", "S", "M", "L", "XL"], PARTIAL_VARIANT_STOCK),
    ("FSH-002", "تی‌شرت و پولوشرت", "پولوشرت کلاسیک مردانه", "Demo Arden", 2290000, 1790000, ["سرمه‌ای"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-003", "تی‌شرت و پولوشرت", "تی‌شرت آستین‌بلند Ribbed", "Demo Vero", 1650000, None, ["کرم", "مشکی", "آجری"], ["XS", "S", "M", "L"], IN_STOCK),
    ("FSH-004", "تی‌شرت و پولوشرت", "تی‌شرت Heavyweight مردانه", "Demo Rowe", 2450000, 1990000, ["سفید"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-005", "تی‌شرت و پولوشرت", "پولوشرت بافت‌دار", "Demo Lunar", 2790000, None, ["سبز خزه‌ای"], ["S", "M", "L", "XL"], OUT_OF_STOCK),

    ("FSH-006", "پیراهن و شومیز", "پیراهن لینن آزاد زنانه", "Demo Mira", 3890000, 2990000, ["سفید", "آبی آسمانی", "زیتونی"], ["XS", "S", "M", "L", "XL"], PARTIAL_VARIANT_STOCK),
    ("FSH-007", "پیراهن و شومیز", "پیراهن Oxford مردانه", "Demo Nova", 3490000, 2890000, ["سفید"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-008", "پیراهن و شومیز", "شومیز راه‌راه کوتاه", "Demo Rowe", 3150000, None, ["آبی", "صورتی"], ["XS", "S", "M", "L"], IN_STOCK),
    ("FSH-009", "پیراهن و شومیز", "Overshirt کتان مردانه", "Demo Arden", 4200000, 3490000, ["خاکی"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-010", "پیراهن و شومیز", "شومیز ساتن زنانه", "Demo Lunar", 3750000, None, ["عاجی"], ["XS", "S", "M", "L", "XL"], OUT_OF_STOCK),

    ("FSH-011", "شلوار پارچه‌ای", "شلوار Wide-leg زنانه", "Demo Rowe", 3950000, 3150000, ["مشکی", "سنگی", "موکا"], ["36", "38", "40", "42", "44"], PARTIAL_VARIANT_STOCK),
    ("FSH-012", "شلوار پارچه‌ای", "شلوار Chino مردانه", "Demo Vero", 4150000, None, ["بژ"], ["30", "32", "34", "36", "38"], IN_STOCK),
    ("FSH-013", "شلوار پارچه‌ای", "شلوار پلیسه زنانه", "Demo Mira", 4450000, 3550000, ["ذغالی", "سرمه‌ای", "کرم"], ["36", "38", "40", "42", "44"], IN_STOCK),
    ("FSH-014", "شلوار پارچه‌ای", "شلوار Cargo یونیسکس", "Demo Arden", 4790000, 3890000, ["زیتونی"], ["S", "M", "L", "XL"], IN_STOCK),
    ("FSH-015", "شلوار پارچه‌ای", "شلوار رسمی Straight مردانه", "Demo Lunar", 4350000, None, ["مشکی"], ["30", "32", "34", "36", "38"], OUT_OF_STOCK),

    ("FSH-016", "شلوار جین", "جین Straight زنانه", "Demo Nova", 4950000, 3950000, ["آبی", "مشکی", "شیری"], ["26", "28", "30", "32"], PARTIAL_VARIANT_STOCK),
    ("FSH-017", "شلوار جین", "جین Slim مردانه", "Demo Rowe", 5250000, None, ["ایندیگو"], ["30", "32", "34", "36", "38"], IN_STOCK),
    ("FSH-018", "شلوار جین", "جین Wide زنانه", "Demo Mira", 5450000, 4350000, ["آبی روشن", "آبی تیره", "مشکی"], ["26", "28", "30", "32"], IN_STOCK),
    ("FSH-019", "شلوار جین", "جین Relaxed مردانه", "Demo Vero", 5690000, 4590000, ["آبی سنگشور"], ["30", "32", "34", "36", "38"], IN_STOCK),
    ("FSH-020", "شلوار جین", "جین Cropped زنانه", "Demo Lunar", 4890000, None, ["گرافیتی"], ["26", "28", "30", "32"], OUT_OF_STOCK),

    ("FSH-021", "هودی و سویشرت", "هودی زیپ‌دار یونیسکس", "Demo Arden", 3890000, 3090000, ["ذغالی", "کرم", "سبز"], ["S", "M", "L", "XL"], PARTIAL_VARIANT_STOCK),
    ("FSH-022", "هودی و سویشرت", "سویشرت Crewneck زنانه", "Demo Nova", 3350000, None, ["یاسی"], ["XS", "S", "M", "L", "XL"], IN_STOCK),
    ("FSH-023", "هودی و سویشرت", "هودی Oversized زنانه", "Demo Mira", 4150000, 3290000, ["مشکی", "شنی", "زرشکی"], ["XS", "S", "M", "L", "XL"], IN_STOCK),
    ("FSH-024", "هودی و سویشرت", "سویشرت ساده مردانه", "Demo Rowe", 3650000, 2950000, ["سرمه‌ای"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-025", "هودی و سویشرت", "سویشرت Quarter-zip", "Demo Lunar", 4450000, None, ["طوسی"], ["S", "M", "L", "XL"], OUT_OF_STOCK),

    ("FSH-026", "کت و ژاکت", "Bomber کوتاه زنانه", "Demo Mira", 6950000, 5490000, ["مشکی", "زیتونی", "سنگی"], ["XS", "S", "M", "L"], PARTIAL_VARIANT_STOCK),
    ("FSH-027", "کت و ژاکت", "Chore Jacket مردانه", "Demo Nova", 6490000, None, ["تنباکویی"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-028", "کت و ژاکت", "ژاکت Quilted زنانه", "Demo Vero", 7250000, 5790000, ["سرمه‌ای", "کرم", "خاکی"], ["XS", "S", "M", "L", "XL"], IN_STOCK),
    ("FSH-029", "کت و ژاکت", "کت جین مردانه", "Demo Arden", 6790000, None, ["آبی متوسط"], ["S", "M", "L", "XL", "XXL"], IN_STOCK),
    ("FSH-030", "کت و ژاکت", "Blazer دو دکمه زنانه", "Demo Lunar", 8250000, None, ["مشکی"], ["36", "38", "40", "42", "44"], OUT_OF_STOCK),

    ("FSH-031", "پالتو و بارانی", "Trench Coat زنانه", "Demo Nova", 9950000, 7890000, ["بژ", "مشکی", "زیتونی"], ["36", "38", "40", "42", "44"], PARTIAL_VARIANT_STOCK),
    ("FSH-032", "پالتو و بارانی", "پالتو پشمی مردانه", "Demo Rowe", 11500000, None, ["ذغالی"], ["48", "50", "52", "54", "56"], IN_STOCK),
    ("FSH-033", "پالتو و بارانی", "بارانی Mac یونیسکس", "Demo Arden", 7850000, 6250000, ["خردلی", "سرمه‌ای", "سنگی"], ["S", "M", "L", "XL"], IN_STOCK),
    ("FSH-034", "پالتو و بارانی", "پالتو کوتاه زنانه", "Demo Mira", 10750000, None, ["شتری"], ["36", "38", "40", "42", "44"], IN_STOCK),
    ("FSH-035", "پالتو و بارانی", "Parka مردانه", "Demo Lunar", 9450000, None, ["زیتونی"], ["S", "M", "L", "XL", "XXL"], OUT_OF_STOCK),

    ("FSH-036", "پیراهن و لباس زنانه", "Shirt Dress میدی", "Demo Mira", 5850000, 4650000, ["سرمه‌ای", "زیتونی", "آجری"], ["38", "40"], PARTIAL_VARIANT_STOCK),
    ("FSH-037", "پیراهن و لباس زنانه", "Wrap Dress میدی", "Demo Nova", 6250000, None, ["سبز زمردی"], ["36", "38"], IN_STOCK),
    ("FSH-038", "پیراهن و لباس زنانه", "Knit Column Dress", "Demo Rowe", 5450000, None, ["کرم", "ذغالی"], ["S", "M"], IN_STOCK),
    ("FSH-039", "پیراهن و لباس زنانه", "Utility Dress کمربندی", "Demo Arden", 6750000, None, ["خاکی"], ["M", "L"], IN_STOCK),
    ("FSH-040", "پیراهن و لباس زنانه", "Pleated Occasion Dress", "Demo Vero", 8950000, None, ["آلویی"], ["38", "40"], OUT_OF_STOCK),

    ("FSH-041", "دامن", "دامن A-Line میدی", "Demo Nova", 4250000, 3350000, ["مشکی", "شتری", "جین"], ["36", "38"], IN_STOCK),
    ("FSH-042", "دامن", "دامن ساتن میدی", "Demo Mira", 4650000, None, ["شامپاینی"], ["38", "40"], IN_STOCK),
    ("FSH-043", "دامن", "دامن پلیسه", "Demo Rowe", 4450000, None, ["سرمه‌ای", "زرشکی"], ["36", "38"], IN_STOCK),
    ("FSH-044", "دامن", "Cargo Maxi Skirt", "Demo Arden", 5150000, None, ["زیتونی"], ["38", "40"], IN_STOCK),
    ("FSH-045", "دامن", "دامن جین میدی", "Demo Lunar", 4750000, None, ["ایندیگو"], ["36", "38"], OUT_OF_STOCK),

    ("FSH-046", "بافت و پلیور", "پلیور Crewneck", "Demo Rowe", 4750000, 3790000, ["جو دوسر", "سرمه‌ای", "سبز"], ["M", "L"], IN_STOCK),
    ("FSH-047", "بافت و پلیور", "Mockneck Sweater", "Demo Nova", 4950000, None, ["ذغالی"], ["S", "M"], IN_STOCK),
    ("FSH-048", "بافت و پلیور", "Cardigan آزاد", "Demo Mira", 5250000, None, ["کرم", "زرشکی", "طوسی"], ["M", "L"], IN_STOCK),
    ("FSH-049", "بافت و پلیور", "Zip Knit مردانه", "Demo Arden", 5650000, None, ["سرمه‌ای"], ["L", "XL"], IN_STOCK),
    ("FSH-050", "بافت و پلیور", "Cable Knit Sweater", "Demo Lunar", 5450000, None, ["شیری"], ["M", "L"], OUT_OF_STOCK),
]

assert len(PRODUCT_MATRIX) == 50


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return (156, 163, 175)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(color, target, amount: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(color, target))


def _placeholder_image_bytes(*, width: int, height: int, bg_hex: str, seed_text: str) -> bytes:
    """تصویرِ Placeholderِ کاملاً محلی و کپی‌رایت-ایمن — بدونِ هیچ فایل/URL
    خارجی. یک پنلِ استودیوییِ خنثی با رنگِ پایهٔ محصول/رنگ؛ هدفِ این فاز
    فقط پرکردنِ اسلاتِ رسانه است، نه شبیه‌سازیِ عکاسیِ واقعی (نگاه کنید به
    Media Contract در دفترچهٔ اجرا — فازِ بعدی این اسلات‌ها را با دارایی‌
    هایِ بصریِ کنترل‌شده جایگزین می‌کند)."""
    seed = hashlib.sha256(seed_text.encode("utf-8")).digest()
    base = _rgb(bg_hex)
    panel = _mix(base, (255, 255, 255), 0.72)
    bg = (247, 246, 243)

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.08)
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=max(16, width // 20), fill=panel)
    shift = (seed[0] % max(1, int(width * 0.05))) - int(width * 0.025)
    cx, cy = width // 2 + shift, height // 2
    r = int(min(width, height) * 0.22)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_mix(base, (255, 255, 255), 0.12))
    draw.rounded_rectangle(
        (cx - r * 0.6, cy + r * 0.5, cx + r * 0.6, cy + r * 1.5), radius=max(8, r // 6),
        fill=_mix(base, (0, 0, 0), 0.05),
    )
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def _uploaded_placeholder(*, filename: str, bg_hex: str, seed_text: str) -> SimpleUploadedFile:
    data = _placeholder_image_bytes(width=600, height=750, bg_hex=bg_hex, seed_text=seed_text)
    return SimpleUploadedFile(filename, data, content_type="image/jpeg")


def _compute_discount_percent(regular_price: int, sale_price: int | None) -> int:
    if not sale_price:
        return 0
    factor = Decimal(sale_price) / Decimal(regular_price)
    percent = (Decimal(100) - factor * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(0, min(100, int(percent)))


class Command(BaseCommand):
    help = (
        "می‌سازد/بازمی‌سازد یک فروشگاهِ Demo کاملاً ایزوله و قطعی (پوشاک، "
        "«Rasti Mode Demo») — Phase 1 (بنیانِ دادهٔ قطعی) برایِ کارِ «Ready "
        "Template Demo Fashion Store». Idempotent، Tenant-scoped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-username", default="",
            help="یوزرنیمِ یک کاربرِ از‌قبل‌موجود که (اختیاری) مالکِ StoreMembership این فروشگاهِ Demo می‌شود.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help=(
                f"پیش از ساختنِ دوباره، فقط Storeِ Demo با اسلاگِ ثابتِ «{STORE_SLUG}» را کاملاً حذف "
                "می‌کند — هیچ آرگومانی برایِ تغییرِ این اسلاگ وجود ندارد؛ ساختاراً امکانِ حذفِ Storeِ دیگری از این دستور نیست."
            ),
        )

    def handle(self, *args, **options):
        owner = None
        owner_username = (options.get("owner_username") or "").strip()
        if owner_username:
            try:
                owner = User.objects.get(username=owner_username)
            except User.DoesNotExist as exc:
                raise CommandError(f"کاربری با یوزرنیمِ «{owner_username}» یافت نشد.") from exc

        if options["reset"]:
            self._reset()

        with transaction.atomic():
            store = self._seed_store()
            self._seed_domain(store)
            if owner is not None:
                self._seed_membership(store, owner)
            vendor = self._seed_vendor(store)
            categories = self._seed_categories(store)
            brands = self._seed_brands(store)
            products = self._seed_products(store, vendor, categories, brands)
            variant_stats = self._seed_variants(products)
            image_count = self._seed_product_images(products)
            collections = self._seed_collections(store, products)

        self.stdout.write(self.style.SUCCESS(
            "seed_ready_template_fashion_demo با موفقیت اجرا شد:\n"
            f"  Store: {store.slug} (admin_subdomain={store.admin_subdomain})\n"
            f"  دسته‌بندی: {Category.objects.filter(store=store).count()}\n"
            f"  برند: {Brand.objects.filter(store=store).count()}\n"
            f"  کالا: {Product.objects.filter(store=store).count()}\n"
            f"  تنوع: {variant_stats['total']} (روی {variant_stats['products_with_variants']} کالا)\n"
            f"  تصویرِ کالا: {image_count}\n"
            f"  کالکشن: {len(collections)}\n"
        ))

    # ------------------------------------------------------------------ Reset

    @transaction.atomic
    def _reset(self) -> None:
        """فقط Storeِ Demo با همینِ اسلاگِ ثابتِ کدشده (``STORE_SLUG``) را
        حذف می‌کند — هرگز هیچ Storeِ دیگری را، فارغ از هر ورودیِ خط‌فرمان
        (چون اصلاً چنین ورودی‌ای پذیرفته نمی‌شود)."""
        existing = Store.objects.filter(slug=STORE_SLUG).first()
        if existing is None:
            self.stdout.write("  --reset: Storeِ Demo از قبل وجود نداشت — چیزی حذف نشد.")
            return
        self.stdout.write(f"  --reset: حذفِ کاملِ Storeِ Demo «{existing.slug}» (pk={existing.pk})…")
        # ترتیبِ امنِ حذف: ابتدا ProductVariant (تا VariantOptionValue که
        # PROTECTِ ProductOptionValue را نگه می‌دارد کَسکید و آزاد شود)،
        # سپس Productها (که با CASCADE به ProductOption/ProductOptionValue
        # می‌رسد و اکنون دیگر توسطِ VariantOptionValueای محافظت نمی‌شوند؛
        # همچنین PROTECTِ Product.category را آزاد می‌کند)، سپس خودِ Store.
        ProductVariant.objects.filter(product__store=existing).delete()
        Product.objects.filter(store=existing).delete()
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
        return store

    def _seed_domain(self, store: Store) -> None:
        from django.conf import settings

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

    # ------------------------------------------------------------------ Vendor/Category/Brand

    def _seed_vendor(self, store: Store) -> Vendor:
        vendor, _ = Vendor.objects.get_or_create(
            store=store, slug=VENDOR["slug"], defaults={"name": VENDOR["name"], "is_active": True},
        )
        return vendor

    def _seed_categories(self, store: Store) -> dict:
        by_name = {}
        for order, name in enumerate(CATEGORY_NAMES):
            slug = slugify(name, allow_unicode=True)
            category, _ = Category.objects.get_or_create(
                store=store, slug=slug, defaults={"name": name, "order": order, "is_active": True},
            )
            by_name[name] = category
        return by_name

    def _seed_brands(self, store: Store) -> dict:
        by_name = {}
        for index, name in enumerate(BRAND_NAMES):
            slug = slugify(name, allow_unicode=True)
            brand, _ = Brand.objects.get_or_create(
                store=store, slug=slug, defaults={"name": name, "sort_order": index, "is_active": True},
            )
            by_name[name] = brand
        return by_name

    # ------------------------------------------------------------------ Products

    def _seed_products(self, store: Store, vendor: Vendor, categories: dict, brands: dict) -> list:
        """دقیقاً ۵۰ کالا — طبقِ ماتریسِ ثابتِ کار. قیمت/تخفیف/موجودیِ کلی
        (``Product.stock``) این‌جا مقداردهیِ اولیه می‌شود؛ موجودیِ واقعیِ
        سطحِ تنوع در ``_seed_variants`` (که موتورِ واقعیِ تنوع را صدا
        می‌زند) محاسبه و روی همین فیلد بازنویسی می‌شود."""
        products = []
        for row in PRODUCT_MATRIX:
            code, category_name, name, brand_name, regular_price, sale_price, colors, sizes, stock_state = row
            category = categories[category_name]
            brand = brands[brand_name]
            slug = f"{slugify(name, allow_unicode=True)}-{code.lower()}"
            discount_percent = _compute_discount_percent(regular_price, sale_price)

            product, created = Product.objects.get_or_create(
                store=store, sku=code,
                defaults={
                    "vendor": vendor, "category": category, "brand": brand,
                    "name": name, "slug": slug,
                    "description": (
                        f"{name} — بخشی از مجموعهٔ نمایشیِ Rasti Mode Demo برایِ آزمونِ واقعیِ "
                        "Storefront در قالب‌های آماده. این یک محصولِ نمایشی است، نه کالایِ واقعیِ فروش."
                    ),
                    "price": regular_price, "discount_percent": discount_percent,
                    "status": Product.Status.ACTIVE,
                    "product_type": Product.ProductType.VARIABLE,
                    "unit": Product.Unit.PIECE,
                },
            )
            if not created:
                # Idempotent re-run: keep price/discount in sync with the
                # fixed matrix without touching anything else (e.g. stock,
                # which _seed_variants recomputes from real variant state).
                changed_fields = []
                if product.discount_percent != discount_percent:
                    product.discount_percent = discount_percent
                    changed_fields.append("discount_percent")
                if int(product.price) != regular_price:
                    product.price = regular_price
                    changed_fields.append("price")
                if product.product_type != Product.ProductType.VARIABLE:
                    product.product_type = Product.ProductType.VARIABLE
                    changed_fields.append("product_type")
                if product.brand_id != brand.id:
                    product.brand = brand
                    changed_fields.append("brand")
                if changed_fields:
                    product.save(update_fields=[*changed_fields, "updated_at"])

            products.append((product, colors, sizes, stock_state))
        return products

    # ------------------------------------------------------------------ Variants

    def _seed_variants(self, products: list) -> dict:
        """برایِ هر کالا، دو محورِ واقعیِ «رنگ»/«سایز» را (اگر هنوز نسازند)
        از طریقِ موتورِ چندمحوره می‌سازد و ``generate_variants`` را صدا
        می‌زند تا ترکیب‌هایِ واقعیِ رنگ×سایز (هرکدام یک ``ProductVariant``
        با ``combination_key`` واقعی) ساخته شوند. سپس موجودیِ هر ترکیب را
        طبقِ ``stock_state`` این کالا تنظیم می‌کند:

        - ``IN_STOCK``: همهٔ ترکیب‌ها موجودی سالم دارند.
        - ``OUT_OF_STOCK``: همهٔ ترکیب‌ها موجودیِ صفر دارند (کالا واقعاً
          غیرِقابل‌خرید است — از طریقِ همان موتورِ موجودیِ واقعی، نه یک
          پرچمِ نمایشی).
        - ``PARTIAL_VARIANT_STOCK``: دقیقاً همان یک ترکیبِ (رنگِ اول ×
          سایزِ اول) موجودیِ صفر می‌گیرد؛ بقیهٔ ترکیب‌ها موجودی سالم دارند
          — کالا در کل قابلِ‌خرید می‌ماند (طبقِ الزامِ صریحِ کار).

        Idempotent: اگر محورهایِ فعالِ کالا از قبل وجود دارند، دوباره
        ساخته نمی‌شوند — فقط ``generate_variants`` (که خودش idempotent
        است) و تنظیمِ موجودی دوباره اجرا می‌شود."""
        total = 0
        products_with_variants = 0

        for product, colors, sizes, stock_state in products:
            if not product.options.filter(is_active=True).exists():
                variant_engine_service.add_product_option(
                    product, label="رنگ", input_type=ProductOption.InputType.COLOR,
                    values=colors,
                    color_hex_by_label={c: COLOR_HEX.get(c, _FALLBACK_COLOR_HEX) for c in colors},
                )
                variant_engine_service.add_product_option(
                    product, label="سایز", values=sizes,
                )

            variant_engine_service.generate_variants(product)

            first_color, first_size = colors[0], sizes[0]
            variants = list(product.variants.filter(is_obsolete=False))
            to_update = []
            product_total_stock = 0
            for variant in variants:
                color_label, _, size_label = variant.value.partition(" / ")
                if stock_state == OUT_OF_STOCK:
                    new_stock = 0
                elif stock_state == PARTIAL_VARIANT_STOCK and color_label == first_color and size_label == first_size:
                    new_stock = 0
                elif stock_state == PARTIAL_VARIANT_STOCK:
                    new_stock = _PARTIAL_HEALTHY_VARIANT_STOCK
                else:
                    new_stock = _HEALTHY_VARIANT_STOCK
                product_total_stock += new_stock
                if variant.stock != new_stock:
                    variant.stock = new_stock
                    to_update.append(variant)
            if to_update:
                ProductVariant.objects.bulk_update(to_update, ["stock"])

            if product.stock != product_total_stock:
                product.stock = product_total_stock
                product.save(update_fields=["stock", "updated_at"])

            total += len(variants)
            if variants:
                products_with_variants += 1

        return {"total": total, "products_with_variants": products_with_variants}

    # ------------------------------------------------------------------ Images

    def _seed_product_images(self, products: list) -> int:
        """دقیقاً ۳ ``ProductImage`` به‌ازایِ هر کالا (= ۱۵۰ کل). برایِ
        کالاهایِ چندرنگ، تا ۳ تصویرِ اول به مقادیرِ محورِ «رنگ» (از طریقِ
        ``option_value`` — نه ``variant``) نگاشت می‌شوند تا سوییچِ خودکارِ
        تصویر با انتخابِ رنگ در فازِ بعد کار کند؛ بقیه (یا کالاهایِ
        تک‌رنگ) تصویرِ عمومیِ کالا می‌مانند. هیچ فایل/URL خارجی مصرف
        نمی‌شود — idempotent (کالایِ دارایِ ۳ تصویر یا بیشتر رد می‌شود)."""
        created_count = 0
        for product, colors, _sizes, _stock_state in products:
            if product.images.count() >= 3:
                continue
            color_option = product.options.filter(label="رنگ", is_active=True).first()
            color_values = list(color_option.values.filter(is_active=True).order_by("display_order")) if color_option else []
            is_multi_color = len(colors) > 1

            for shot in range(3):
                bg_hex = COLOR_HEX.get(colors[shot % len(colors)], _FALLBACK_COLOR_HEX)
                image = add_product_image(
                    product,
                    _uploaded_placeholder(
                        filename=f"{product.slug}-{shot}.jpg", bg_hex=bg_hex,
                        seed_text=f"{product.sku}-{shot}",
                    ),
                    alt=f"{product.name} — تصویر {shot + 1}",
                )
                if is_multi_color and shot < len(color_values):
                    set_image_option_value(image, color_values[shot])
                created_count += 1
        return created_count

    # ------------------------------------------------------------------ Collections

    def _seed_collections(self, store: Store, products: list) -> list:
        """چهار کالکشنِ دستیِ خنثی — طبقِ الزامِ صریحِ کار. عضویت‌ها قطعی
        (نه تصادفی) هستند تا اجرایِ دوباره همیشه همان نتیجه را بدهد:
        «جدیدترین‌ها»یِ ۱۰ کالایِ آخرِ ماتریس، «پرفروش‌ها»یِ ۱۰ کالایِ اول،
        «تخفیف‌های منتخب» یعنی همهٔ کالاهایِ تخفیف‌دار، «انتخاب فصل» یک
        زیرمجموعهٔ ثابتِ ۱۰تایی از میانهٔ ماتریس."""
        all_products = [p for p, *_ in products]
        discounted = [p for p in all_products if p.discount_percent > 0]
        member_map = {
            "جدیدترین‌ها": all_products[-10:],
            "پرفروش‌ها": all_products[:10],
            "تخفیف‌های منتخب": discounted,
            "انتخاب فصل": all_products[20:30],
        }

        collections = []
        for definition in COLLECTIONS:
            name = definition["name"]
            collection, _ = MerchantCollection.objects.get_or_create(
                store=store, name=name,
                defaults={
                    "slug": slugify(name, allow_unicode=True),
                    "description": definition["description"],
                    "is_active": True,
                },
            )
            collection_service.add_products(collection, member_map[name])
            collections.append(collection)
        return collections
