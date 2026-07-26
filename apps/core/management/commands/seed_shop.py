"""دستور idempotent برای پر کردن دیتابیس با داده‌ی نمونه‌ی جنریک.

اجرا: python manage.py seed_shop
اجرای دوباره‌ی این دستور نباید رکورد تکراری بسازد (idempotent) — همه‌جا از
get_or_create روی فیلد یکتا استفاده می‌شود، و بخش سفارش‌های نمونه فقط در
صورتی اجرا می‌شود که فروشنده هنوز هیچ سفارشی نداشته باشد.
"""

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.blog.models import BlogPost
from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Brand, Category, Product, ProductVariant, Vendor
from apps.catalog.services.product_image_service import add_product_image
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import change_order_status, create_order_from_cart
from apps.orders.services.payment_service import simulate_payment
from apps.stores.models import Store

User = get_user_model()

# محصولاتی که برای نمایش عملی گالری/کاور یک تصویر نمونه می‌گیرند — بقیه‌ی
# محصولات عمداً بدون تصویر می‌مانند تا fallback آیکون/رنگ هم قابل مشاهده باشد.
SEED_IMAGE_SKUS = ["HA-IRON-001", "DG-PHONE-001", "CL-SNEAKER-002", "CL-BAG-003"]


def _darken_hex(hex_color: str, factor: float) -> tuple:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(max(0, int(channel * (1 - factor))) for channel in (r, g, b))

VENDOR = {"name": "فروشگاه چندمنظوره دیجی‌مارکت", "slug": "digimarket"}

CATEGORIES = [
    {
        "name": "لوازم خانگی", "slug": "home-appliances", "icon": "🏠",
        "children": [
            {"name": "آشپزخانه", "slug": "kitchen", "icon": "🍳"},
            {"name": "لوازم برقی", "slug": "electrical", "icon": "🔌"},
        ],
    },
    {
        "name": "لوازم‌تحریر", "slug": "stationery", "icon": "✏️",
        "children": [
            {"name": "نوشت‌افزار", "slug": "writing-tools", "icon": "🖊️"},
            {"name": "کیف و کوله", "slug": "bags", "icon": "🎒"},
        ],
    },
    {
        "name": "میوه و سبزیجات", "slug": "fruits-vegetables", "icon": "🍎",
        "children": [
            {"name": "میوه", "slug": "fruits", "icon": "🍇"},
            {"name": "سبزیجات", "slug": "vegetables", "icon": "🥕"},
        ],
    },
    {
        "name": "دیجیتال", "slug": "digital", "icon": "📱",
        "children": [
            {"name": "موبایل", "slug": "mobile", "icon": "📱"},
            {"name": "لوازم جانبی دیجیتال", "slug": "digital-accessories", "icon": "🎧"},
        ],
    },
    {
        "name": "پوشاک", "slug": "clothing", "icon": "👕",
        "children": [
            {"name": "مردانه", "slug": "men-clothing", "icon": "👔"},
            {"name": "زنانه", "slug": "women-clothing", "icon": "👗"},
        ],
    },
]

BRANDS = [
    {"name": "بوش", "slug": "bosch"},
    {"name": "پارس خزر", "slug": "pars-khazar"},
    {"name": "فابر کاستل", "slug": "faber-castell"},
    {"name": "شیائومی", "slug": "xiaomi"},
    {"name": "نایکی", "slug": "nike"},
]

# هر محصول: category_slug، brand_slug (یا None)، بقیه‌ی فیلدهای Product و variants اختیاری
PRODUCTS = [
    {
        "category": "electrical", "brand": "bosch", "name": "اتو بخار بوش", "slug": "bosch-steam-iron",
        "sku": "HA-IRON-001", "description": "اتو بخار قدرتمند با کف سرامیکی و بخار پیوسته.",
        "price": Decimal("2200000"), "discount_percent": 15, "stock": 12, "tag": Product.Tag.HOT,
        "icon": "🔌", "tint": "#e0f2fe", "rating": Decimal("4.50"), "reviews_count": 34, "sold_count": 120,
        "views_count": 980,
    },
    {
        "category": "kitchen", "brand": "pars-khazar", "name": "پلوپز پارس خزر", "slug": "parskhazar-rice-cooker",
        "sku": "HA-RICE-002", "description": "پلوپز ۸ نفره با پخت یکنواخت و دیگ آنودایز.",
        "price": Decimal("3450000"), "discount_percent": 0, "stock": 8, "tag": Product.Tag.NEW,
        "icon": "🍚", "tint": "#fef3c7", "rating": Decimal("4.20"), "reviews_count": 18, "sold_count": 45,
        "views_count": 510,
    },
    {
        "category": "kitchen", "brand": "pars-khazar", "name": "چای‌ساز پارس خزر", "slug": "parskhazar-tea-maker",
        "sku": "HA-TEA-003", "description": "چای‌ساز دو کتری با گرم‌نگه‌دارنده.",
        "price": Decimal("1850000"), "discount_percent": 10, "stock": 0, "tag": "",
        "icon": "☕", "tint": "#fde68a", "rating": Decimal("3.90"), "reviews_count": 9, "sold_count": 22,
        "views_count": 300,
    },
    {
        "category": "writing-tools", "brand": "faber-castell", "name": "دفتر یادداشت چرمی",
        "slug": "leather-notebook", "sku": "ST-NOTE-001", "description": "دفتر یادداشت جلد چرمی ۱۰۰ برگ.",
        "price": Decimal("320000"), "discount_percent": 0, "stock": 40, "tag": "",
        "icon": "📓", "tint": "#f1ecfd", "rating": Decimal("4.60"), "reviews_count": 12, "sold_count": 60,
        "views_count": 220,
    },
    {
        "category": "writing-tools", "brand": "faber-castell", "name": "خودکار فابر کاستل",
        "slug": "faber-castell-pen", "sku": "ST-PEN-002", "description": "خودکار روان‌نویس با جوهر تمیزنویس.",
        "price": Decimal("95000"), "discount_percent": 20, "stock": 150, "tag": Product.Tag.SALE,
        "icon": "🖊️", "tint": "#e0e7ff", "rating": Decimal("4.10"), "reviews_count": 27, "sold_count": 310,
        "views_count": 700,
    },
    {
        "category": "bags", "brand": None, "name": "کیف مدرسه کوله‌پشتی", "slug": "school-backpack",
        "sku": "ST-BAG-003", "description": "کوله‌پشتی مدرسه ضدآب با چند جیب.",
        "price": Decimal("780000"), "discount_percent": 5, "stock": 25, "tag": "",
        "icon": "🎒", "tint": "#ffe4e6", "rating": Decimal("4.00"), "reviews_count": 14, "sold_count": 70,
        "views_count": 400,
    },
    {
        "category": "fruits", "brand": None, "name": "سیب قرمز درجه‌یک", "slug": "red-apple",
        "sku": "FR-APPLE-001", "description": "سیب قرمز تازه و درجه‌یک، ارسال روزانه.",
        "price": Decimal("85000"), "discount_percent": 0, "stock": 300, "tag": Product.Tag.NEW,
        "icon": "🍎", "tint": "#fee2e2", "rating": Decimal("4.70"), "reviews_count": 41, "sold_count": 500,
        "views_count": 1200,
        "variants": [
            {"attribute": "وزن", "value": "۱ کیلوگرم", "stock": 150, "extra_price": Decimal("0")},
            {"attribute": "وزن", "value": "۵ کیلوگرم", "stock": 150, "extra_price": Decimal("380000")},
        ],
    },
    {
        "category": "fruits", "brand": None, "name": "موز", "slug": "banana",
        "sku": "FR-BANANA-002", "description": "موز درجه‌یک وارداتی.",
        "price": Decimal("65000"), "discount_percent": 0, "stock": 200, "tag": "",
        "icon": "🍌", "tint": "#fef9c3", "rating": Decimal("4.30"), "reviews_count": 15, "sold_count": 260,
        "views_count": 600,
    },
    {
        "category": "vegetables", "brand": None, "name": "گوجه‌فرنگی", "slug": "tomato",
        "sku": "FR-TOMATO-003", "description": "گوجه‌فرنگی تازه‌ی گلخانه‌ای.",
        "price": Decimal("45000"), "discount_percent": 0, "stock": 0, "tag": "",
        "icon": "🍅", "tint": "#fee2e2", "rating": Decimal("3.80"), "reviews_count": 6, "sold_count": 90,
        "views_count": 250,
    },
    {
        "category": "mobile", "brand": "xiaomi", "name": "گوشی شیائومی ردمی نوت", "slug": "xiaomi-redmi-note",
        "sku": "DG-PHONE-001", "description": "گوشی هوشمند با دوربین ۱۰۸ مگاپیکسل و باتری پرقدرت.",
        "price": Decimal("12500000"), "discount_percent": 8, "stock": 20, "tag": Product.Tag.HOT,
        "icon": "📱", "tint": "#eceef3", "rating": Decimal("4.60"), "reviews_count": 88, "sold_count": 340,
        "views_count": 3100,
        "variants": [
            {"attribute": "رنگ", "value": "مشکی", "value_hex": "#1f2937", "stock": 10, "extra_price": Decimal("0")},
            {"attribute": "رنگ", "value": "آبی", "value_hex": "#2563eb", "stock": 10, "extra_price": Decimal("0")},
        ],
    },
    {
        "category": "digital-accessories", "brand": "xiaomi", "name": "هندزفری بلوتوث شیائومی",
        "slug": "xiaomi-bluetooth-earbuds", "sku": "DG-EARBUD-002",
        "description": "هندزفری بی‌سیم با کیفیت صدای بالا و باتری ۲۴ ساعته.",
        "price": Decimal("1200000"), "discount_percent": 30, "stock": 55, "tag": Product.Tag.SALE,
        "icon": "🎧", "tint": "#e0e7ff", "rating": Decimal("4.40"), "reviews_count": 52, "sold_count": 410,
        "views_count": 1900,
    },
    {
        "category": "digital-accessories", "brand": None, "name": "پاوربانک ۲۰۰۰۰", "slug": "powerbank-20000",
        "sku": "DG-POWER-003", "description": "پاوربانک ۲۰۰۰۰ میلی‌آمپر با شارژ سریع.",
        "price": Decimal("950000"), "discount_percent": 0, "stock": 33, "tag": "",
        "icon": "🔋", "tint": "#dcfce7", "rating": Decimal("4.10"), "reviews_count": 19, "sold_count": 150,
        "views_count": 800,
    },
    {
        "category": "men-clothing", "brand": "nike", "name": "هودی مشکی یونی‌سکس کلاه‌دار", "slug": "black-unisex-hoodie",
        "sku": "CL-HOODIE-001", "description": "هودی نخی گرم مناسب فصل سرد، طرح یونی‌سکس.",
        "price": Decimal("1800000"), "discount_percent": 19, "stock": 27, "tag": Product.Tag.NEW,
        "icon": "🧥", "tint": "#e9ebf1", "rating": Decimal("4.50"), "reviews_count": 61, "sold_count": 210,
        "views_count": 1400,
        "variants": [
            {"attribute": "رنگ", "value": "مشکی", "value_hex": "#1f2937", "stock": 15, "extra_price": Decimal("0")},
            {"attribute": "سایز", "value": "L", "stock": 12, "extra_price": Decimal("0")},
        ],
    },
    {
        "category": "men-clothing", "brand": "nike", "name": "کتانی اسپرت مردانه سفید", "slug": "white-sport-sneaker",
        "sku": "CL-SNEAKER-002", "description": "کتانی اسپرت سبک با زیره‌ی ضدلغزش.",
        "price": Decimal("4200000"), "discount_percent": 18, "stock": 18, "tag": Product.Tag.HOT,
        "icon": "👟", "tint": "#eceef3", "rating": Decimal("4.70"), "reviews_count": 73, "sold_count": 380,
        "views_count": 2200,
        "variants": [
            {"attribute": "سایز", "value": "۴۰", "stock": 6, "extra_price": Decimal("0")},
            {"attribute": "سایز", "value": "۴۲", "stock": 6, "extra_price": Decimal("0")},
            {"attribute": "سایز", "value": "۴۴", "stock": 6, "extra_price": Decimal("0")},
        ],
    },
    {
        "category": "women-clothing", "brand": None, "name": "کیف دوشی زنانه چرم طبیعی", "slug": "women-leather-bag",
        "sku": "CL-BAG-003", "description": "کیف دوشی چرم طبیعی با دوخت دست‌دوز.",
        "price": Decimal("2280000"), "discount_percent": 0, "stock": 14, "tag": Product.Tag.SALE,
        "icon": "👜", "tint": "#fdeaf0", "rating": Decimal("4.30"), "reviews_count": 29, "sold_count": 95,
        "views_count": 900,
    },
]

CUSTOMERS = [
    {"username": "ali_rezaei", "full_name": "علی رضایی", "phone": "09121110001", "city": "تهران", "is_vip": True},
    {"username": "sara_ahmadi", "full_name": "سارا احمدی", "phone": "09121110002", "city": "اصفهان", "is_vip": False},
    {"username": "mohammad_karimi", "full_name": "محمد کریمی", "phone": "09121110003", "city": "شیراز", "is_vip": True},
    {"username": "zahra_hosseini", "full_name": "زهرا حسینی", "phone": "09121110004", "city": "مشهد", "is_vip": False},
    {"username": "reza_nouri", "full_name": "رضا نوری", "phone": "09121110005", "city": "تبریز", "is_vip": False},
]
DEFAULT_PASSWORD = "Passw0rd!123"

SHIPPING_METHODS = [
    {"name": "پست پیشتاز", "slug": "post", "description": "تحویل ۲ تا ۴ روز کاری", "cost": Decimal("45000"), "icon": "📦"},
    {"name": "تیپاکس", "slug": "tipax", "description": "تحویل ۱ تا ۳ روز کاری", "cost": Decimal("65000"), "icon": "🚀"},
    {"name": "پیک موتوری", "slug": "peyk", "description": "تحویل همان روز (ویژه تهران)", "cost": Decimal("80000"), "icon": "🛵"},
]

PAYMENT_GATEWAYS = [
    {"name": "زرین‌پال", "slug": "zarin", "description": "پرداخت امن آنلاین — همه کارت‌ها", "icon": "🟡", "fee_percent": Decimal("1.5")},
    {"name": "پی‌پینگ", "slug": "payping", "description": "پرداخت با کیف پول و اقساط", "icon": "🟢", "fee_percent": Decimal("1.2")},
    {"name": "به‌پرداخت ملت", "slug": "mellat", "description": "درگاه مستقیم بانکی", "icon": "🔴", "fee_percent": Decimal("1.0")},
    {"name": "کیف پول دیجی‌مارکت", "slug": "wallet", "description": "پرداخت از موجودی کیف پول", "icon": "👛", "fee_percent": Decimal("0")},
]

COUPONS = [
    {"code": "WELCOME10", "type": Coupon.Type.PERCENT, "value": Decimal("10"), "label": "۱۰٪ تخفیف اولین خرید"},
    {"code": "STYLE20", "type": Coupon.Type.PERCENT, "value": Decimal("20"), "label": "۲۰٪ تخفیف ویژه"},
    {"code": "DIGI50", "type": Coupon.Type.FIXED, "value": Decimal("500000"), "label": "۵۰۰٬۰۰۰ تومان تخفیف"},
    {"code": "FREESHIP", "type": Coupon.Type.FREE_SHIP, "value": Decimal("0"), "label": "ارسال رایگان"},
]

BLOG_POSTS = [
    {
        "title": "۵ نکته برای نگهداری از لوازم خانگی برقی", "slug": "home-appliance-care-tips",
        "category_label": "راهنمای خرید", "cover_emoji": "🏠", "tint": "#f1ecfd",
        "excerpt": "با رعایت چند نکته‌ی ساده، عمر لوازم خانگی برقی خود را افزایش دهید.",
        "body": "متن کامل مطلب درباره‌ی نگهداری از لوازم خانگی برقی...",
    },
    {
        "title": "چگونه میوه و سبزیجات را تازه نگه داریم", "slug": "keep-produce-fresh",
        "category_label": "سبک زندگی", "cover_emoji": "🍎", "tint": "#fee2e2",
        "excerpt": "راهکارهای ساده برای نگهداری طولانی‌مدت میوه و سبزیجات تازه.",
        "body": "متن کامل مطلب درباره‌ی نگهداری میوه و سبزیجات...",
    },
    {
        "title": "راهنمای انتخاب گوشی هوشمند مناسب", "slug": "smartphone-buying-guide",
        "category_label": "تکنولوژی", "cover_emoji": "📱", "tint": "#eceef3",
        "excerpt": "قبل از خرید گوشی جدید، این نکات را در نظر بگیرید.",
        "body": "متن کامل مطلب درباره‌ی انتخاب گوشی هوشمند...",
    },
    {
        "title": "ترندهای پوشاک بهار ۱۴۰۵", "slug": "spring-1405-fashion-trends",
        "category_label": "مد و پوشاک", "cover_emoji": "👗", "tint": "#fdeaf0",
        "excerpt": "نگاهی به جدیدترین ترندهای پوشاک در فصل بهار.",
        "body": "متن کامل مطلب درباره‌ی ترندهای پوشاک بهار...",
    },
]


class Command(BaseCommand):
    help = "دیتابیس را با داده‌ی نمونه‌ی جنریک (چند دسته و نوع کالای متفاوت) پر می‌کند. idempotent است."

    @transaction.atomic
    def handle(self, *args, **options):
        # این دستور همیشه فقط داده‌ی نمایشی Akhlaghi را seed می‌کند — Store
        # به‌طور صریح با اسلاگ resolve می‌شود، نه حالت سازگاری موقت (که به
        # درخواست HTTP نیاز دارد و اینجا اصلاً وجود ندارد).
        store = Store.objects.get(slug="akhlaghi")
        vendor = self._seed_vendor(store)
        categories = self._seed_categories(store)
        brands = self._seed_brands(store)
        products = self._seed_products(store, vendor, categories, brands)
        self._seed_product_images(products)
        customers = self._seed_customers()
        shipping_methods = self._seed_shipping_methods(store)
        gateways = self._seed_payment_gateways(store)
        coupons = self._seed_coupons()
        self._seed_orders(store, vendor, customers, products, shipping_methods, gateways, coupons)
        self._seed_blog_posts()
        self._recompute_customer_stats()

        self.stdout.write(self.style.SUCCESS(
            "seed_shop با موفقیت اجرا شد: "
            f"{Category.objects.count()} دسته، {Brand.objects.count()} برند، "
            f"{Product.objects.count()} کالا، {Customer.objects.count()} مشتری، "
            f"{Order.objects.count()} سفارش، {BlogPost.objects.count()} مطلب وبلاگ."
        ))

    # ------------------------------------------------------------------
    def _seed_vendor(self, store):
        vendor, created = Vendor.objects.get_or_create(
            store=store, slug=VENDOR["slug"], defaults={"name": VENDOR["name"], "is_active": True}
        )
        self._log("فروشنده", 1 if created else 0)
        return vendor

    def _seed_categories(self, store):
        by_slug = {}
        created_count = 0
        for order, top in enumerate(CATEGORIES):
            parent, created = Category.objects.get_or_create(
                store=store, slug=top["slug"],
                defaults={"name": top["name"], "icon": top["icon"], "order": order},
            )
            created_count += created
            by_slug[top["slug"]] = parent
            for child_order, child in enumerate(top.get("children", [])):
                child_obj, child_created = Category.objects.get_or_create(
                    store=store, slug=child["slug"],
                    defaults={
                        "name": child["name"], "icon": child["icon"],
                        "parent": parent, "order": child_order,
                    },
                )
                created_count += child_created
                by_slug[child["slug"]] = child_obj
        self._log("دسته‌بندی", created_count)
        return by_slug

    def _seed_brands(self, store):
        by_slug = {}
        created_count = 0
        for data in BRANDS:
            brand, created = Brand.objects.get_or_create(
                store=store, slug=data["slug"], defaults={"name": data["name"]}
            )
            created_count += created
            by_slug[data["slug"]] = brand
        self._log("برند", created_count)
        return by_slug

    def _seed_products(self, store, vendor, categories, brands):
        by_sku = {}
        created_count = 0
        for source in PRODUCTS:
            data = dict(source)  # کپی سطحی تا دیکشنری ماژول‌سطحی تغییر نکند (لازم برای اجرای چندباره)
            variants = data.pop("variants", [])
            category = categories[data.pop("category")]
            brand_slug = data.pop("brand")
            brand = brands[brand_slug] if brand_slug else None

            product, created = Product.objects.get_or_create(
                store=store, sku=data["sku"],
                defaults={
                    **{k: v for k, v in data.items() if k != "sku"},
                    "vendor": vendor, "category": category, "brand": brand,
                },
            )
            created_count += created
            by_sku[data["sku"]] = product

            if created and variants:
                for variant_data in variants:
                    ProductVariant.objects.get_or_create(
                        product=product, attribute=variant_data["attribute"], value=variant_data["value"],
                        defaults={
                            "value_hex": variant_data.get("value_hex", ""),
                            "stock": variant_data.get("stock", 0),
                            "extra_price": variant_data.get("extra_price", Decimal("0")),
                        },
                    )
                product.product_type = Product.ProductType.VARIABLE
                product.save(update_fields=["product_type"])
        self._log("کالا", created_count)
        return by_sku

    def _seed_product_images(self, products):
        """برای چند محصول منتخب یک تصویر نمونه از طریق سرویس واقعی آپلود می‌سازد (idempotent).

        اگر محصولی از قبل تصویر داشته باشد رد می‌شود؛ محصولاتی که در
        SEED_IMAGE_SKUS نیستند عمداً بدون تصویر می‌مانند تا fallback
        آیکون/رنگ کارت محصول هم در دیتای نمونه قابل مشاهده بماند.
        """
        tint_by_sku = {data["sku"]: data.get("tint", "#eceef3") for data in PRODUCTS}
        created_count = 0
        for sku in SEED_IMAGE_SKUS:
            product = products.get(sku)
            if product is None or product.images.exists():
                continue
            base_color = tint_by_sku.get(sku, "#eceef3")
            img = Image.new("RGB", (900, 900), base_color)
            # دایره‌ی تیره‌تر تا تصویر نمونه از رنگ پس‌زمینه‌ی کارت (fallback) قابل‌تشخیص باشد
            ImageDraw.Draw(img).ellipse((160, 160, 740, 740), fill=_darken_hex(base_color, 0.35))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            file = SimpleUploadedFile(f"{product.slug}-seed.jpg", buffer.getvalue(), content_type="image/jpeg")
            add_product_image(product, file, alt=product.name)
            created_count += 1
        self._log("تصویر نمونه‌ی کالا", created_count)

    def _seed_customers(self):
        by_username = {}
        created_count = 0
        for data in CUSTOMERS:
            user, user_created = User.objects.get_or_create(
                username=data["username"], defaults={"email": f"{data['username']}@example.com"}
            )
            if user_created:
                user.set_password(DEFAULT_PASSWORD)
                user.save()

            customer, customer_created = Customer.objects.get_or_create(
                user=user,
                defaults={
                    "full_name": data["full_name"], "phone": data["phone"],
                    "city": data["city"], "is_vip": data["is_vip"],
                },
            )
            created_count += customer_created
            by_username[data["username"]] = customer

            Address.objects.get_or_create(
                customer=customer, is_default=True,
                defaults={
                    "receiver_name": data["full_name"], "phone": data["phone"],
                    "province": data["city"], "city": data["city"],
                    "postal_code": "1111111111", "full_address": f"{data['city']}، خیابان اصلی، پلاک ۱",
                },
            )
        self._log("مشتری", created_count)
        return by_username

    def _seed_shipping_methods(self, store):
        by_slug = {}
        created_count = 0
        for data in SHIPPING_METHODS:
            method, created = ShippingMethod.objects.get_or_create(
                store=store, slug=data["slug"],
                defaults={
                    "name": data["name"], "description": data["description"],
                    "cost": data["cost"], "icon": data["icon"], "is_active": True,
                },
            )
            created_count += created
            by_slug[data["slug"]] = method
        self._log("روش ارسال", created_count)
        return by_slug

    def _seed_payment_gateways(self, store):
        by_slug = {}
        created_count = 0
        for data in PAYMENT_GATEWAYS:
            gateway, created = PaymentGateway.objects.get_or_create(
                store=store, slug=data["slug"],
                defaults={
                    "name": data["name"], "description": data["description"],
                    "icon": data["icon"], "fee_percent": data["fee_percent"], "is_active": True,
                },
            )
            created_count += created
            by_slug[data["slug"]] = gateway
        self._log("درگاه پرداخت", created_count)
        return by_slug

    def _seed_coupons(self):
        by_code = {}
        created_count = 0
        for data in COUPONS:
            coupon, created = Coupon.objects.get_or_create(
                code=data["code"],
                defaults={"type": data["type"], "value": data["value"], "label": data["label"]},
            )
            created_count += created
            by_code[data["code"]] = coupon
        self._log("کد تخفیف", created_count)
        return by_code

    def _seed_orders(self, store, vendor, customers, products, shipping_methods, gateways, coupons):
        if Order.objects.filter(vendor=vendor).exists():
            self._log("سفارش نمونه", 0, note="از قبل موجود بود")
            return

        plans = [
            {
                "customer": "ali_rezaei", "items": [("DG-PHONE-001", 1), ("DG-EARBUD-002", 1)],
                "coupon": "WELCOME10", "shipping": "post", "gateway": "zarin",
                "flow": ["pay_success", "shipped", "delivered"],
            },
            {
                "customer": "sara_ahmadi", "items": [("CL-HOODIE-001", 1), ("CL-SNEAKER-002", 1)],
                "coupon": None, "shipping": "tipax", "gateway": "payping",
                "flow": ["pay_success", "shipped"],
            },
            {
                "customer": "mohammad_karimi", "items": [("HA-RICE-002", 1), ("HA-IRON-001", 1)],
                "coupon": "STYLE20", "shipping": "peyk", "gateway": "mellat",
                "flow": ["pay_success"],
            },
            {
                "customer": "zahra_hosseini", "items": [("ST-NOTE-001", 2), ("ST-PEN-002", 3)],
                "coupon": None, "shipping": "post", "gateway": "wallet",
                "flow": [],
            },
            {
                "customer": "reza_nouri", "items": [("FR-APPLE-001", 2), ("FR-BANANA-002", 3)],
                "coupon": "DIGI50", "shipping": "post", "gateway": "zarin",
                "flow": ["pay_fail", "cancel"],
            },
            {
                "customer": "ali_rezaei", "items": [("DG-POWER-003", 1), ("CL-BAG-003", 1)],
                "coupon": "FREESHIP", "shipping": "post", "gateway": "payping",
                "flow": ["pay_success", "shipped", "delivered"],
            },
        ]

        created_count = 0
        for plan in plans:
            customer = customers[plan["customer"]]
            address = customer.addresses.filter(is_default=True).first()
            cart = Cart.objects.create(customer=customer)
            for sku, qty in plan["items"]:
                product = products[sku]
                CartItem.objects.create(cart=cart, product=product, quantity=qty, unit_price=product.final_price)

            coupon = coupons[plan["coupon"]] if plan["coupon"] else None
            order = create_order_from_cart(
                cart, customer=customer, vendor=vendor, address=address,
                shipping_method=shipping_methods[plan["shipping"]],
                payment_gateway=gateways[plan["gateway"]], coupon=coupon,
                store=store,
            )
            cart.delete()
            created_count += 1

            for step in plan["flow"]:
                if step == "pay_success":
                    simulate_payment(order, True, store=store)
                elif step == "pay_fail":
                    simulate_payment(order, False, store=store)
                elif step == "cancel":
                    change_order_status(order, Order.Status.CANCELED, note="مشتری انصراف داد", store=store)
                else:
                    change_order_status(order, step, store=store)

        self._log("سفارش نمونه", created_count)

    def _seed_blog_posts(self):
        created_count = 0
        now = timezone.now()
        for index, data in enumerate(BLOG_POSTS):
            _, created = BlogPost.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "title": data["title"], "category_label": data["category_label"],
                    "cover_emoji": data["cover_emoji"], "tint": data["tint"],
                    "excerpt": data["excerpt"], "body": data["body"],
                    "published_at": now - timezone.timedelta(days=index * 3),
                },
            )
            created_count += created
        self._log("مطلب وبلاگ", created_count)

    def _recompute_customer_stats(self):
        for customer in Customer.objects.all():
            orders = Order.objects.filter(customer=customer)
            spent = sum(
                (o.grand_total for o in orders.exclude(status=Order.Status.CANCELED)), Decimal("0")
            )
            customer.orders_count = orders.count()
            customer.total_spent = spent
            customer.save(update_fields=["orders_count", "total_spent"])

    def _log(self, label, created_count, note=""):
        if note:
            self.stdout.write(f"  {label}: {note}")
        else:
            self.stdout.write(f"  {label}: {created_count} رکورد جدید ساخته شد")
