"""ساخت یک فروشگاه QA محلی با تراکم/ساختار فروشگاهی نزدیک به KianStock.

هدف این command فقط QA بصری/تعاملی در DEBUG=True است. نام‌ها، دسته‌بندی‌ها
و قیمت‌های کوتاهِ کاتالوگی از اطلاعات عمومی فروشگاه مرجع الهام گرفته‌اند؛
عکس‌ها، توضیحات بلند، رضایت‌نامه‌ها و دارایی‌های اختصاصی سایت ثالث کپی
نمی‌شوند و به‌صورت synthetic محلی تولید می‌شوند.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw

from apps.catalog.models import Brand, Category, MerchantCollection, MerchantCollectionItem, Product, Vendor
from apps.catalog.services.product_image_service import add_product_image, set_image_variant
from apps.catalog.services.variant_service import create_variant
from apps.content.models import (
    ContentPage, DestinationType, FooterSettings, HeroSlide, Menu, MenuItem,
    PromotionalBanner, SocialLink, StoryRailItem,
)
from apps.core.models import ShopSettings
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service
from apps.stores.hostnames import normalize_admin_subdomain
from apps.stores.models import Store
from apps.stores.management.commands.seed_rastisi_fashion_demo import Command as FashionSeedCommand

from .kianstock_qa_data import BRANDS, COLLECTIONS, PRODUCTS, TOP_CATEGORIES

User = get_user_model()

STORE_SLUG = "kianstock-qa"
STORE_NAME = "کیان استوک"
STORE_ADMIN_SUBDOMAIN = "kianstock-qa"
PUBLIC_PHONE = "09361428775"
KIDS_PHONE = "09147992815"
PERFUME_PHONE = "09383850097"
GLASSES_PHONE = "09370148628"
SUPPORT_HOURS = "هفت روز هفته، ساعت ۱۰ تا ۱۴ و ۱۶ تا ۲۱"

COLLECTION_TITLES = dict(COLLECTIONS)

# رنگ‌های نزدیک به فروشگاه‌های stock/minimal؛ عکس‌ها عمداً synthetic هستند.
CATEGORY_COLORS = {
    "women": (244, 231, 229), "men": (228, 232, 236), "kids": (250, 238, 212),
    "sports": (223, 236, 229), "perfume": (232, 225, 240), "sneakers": (231, 233, 235),
    "footwear": (236, 228, 219), "sunglasses": (225, 231, 235),
    "accessories": (238, 229, 219), "outlet": (245, 220, 220),
}


def _jpeg_upload(filename: str, *, width: int, height: int, kind: str, index: int = 0) -> SimpleUploadedFile:
    """دارایی QA مستقل: هیچ فایل تصویری از سایت مرجع دانلود نمی‌شود."""
    base = CATEGORY_COLORS.get(kind, (238, 238, 238))
    # تغییر کوچک deterministic برای اینکه ۲۰۰ عکس یکسان نباشند.
    delta = (index * 17) % 24
    bg = tuple(max(0, min(255, c + (delta - 12))) for c in base)
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    ink = (30, 30, 30)
    soft = (255, 255, 255)
    cx, cy = width // 2, height // 2

    if kind in {"sneakers", "footwear"}:
        # فرم ساده کفش
        draw.rounded_rectangle((width*.18, height*.52, width*.78, height*.68), radius=height*.06, fill=soft, outline=ink, width=max(2, width//180))
        draw.polygon([(width*.18, height*.52), (width*.42, height*.38), (width*.62, height*.48), (width*.78, height*.52)], fill=soft, outline=ink)
        draw.line((width*.24, height*.62, width*.79, height*.62), fill=ink, width=max(2, width//160))
    elif kind == "sunglasses":
        r = min(width, height) * .17
        draw.ellipse((cx-r*2.2, cy-r, cx-.15*r, cy+r), fill=(45,45,45), outline=ink, width=4)
        draw.ellipse((cx+.15*r, cy-r, cx+r*2.2, cy+r), fill=(45,45,45), outline=ink, width=4)
        draw.line((cx-.15*r, cy, cx+.15*r, cy), fill=ink, width=6)
        draw.line((cx-r*2.2, cy-.2*r, width*.12, height*.38), fill=ink, width=5)
        draw.line((cx+r*2.2, cy-.2*r, width*.88, height*.38), fill=ink, width=5)
    elif kind == "perfume":
        bw, bh = width*.36, height*.42
        draw.rounded_rectangle((cx-bw/2, cy-bh/2, cx+bw/2, cy+bh/2), radius=width*.03, fill=soft, outline=ink, width=4)
        draw.rectangle((cx-width*.08, cy-bh/2-height*.08, cx+width*.08, cy-bh/2), fill=ink)
        draw.line((cx-width*.13, cy, cx+width*.13, cy), fill=ink, width=3)
    elif kind == "accessories":
        draw.rounded_rectangle((width*.25, height*.42, width*.75, height*.70), radius=width*.04, fill=soft, outline=ink, width=4)
        draw.arc((width*.34, height*.28, width*.66, height*.52), 180, 360, fill=ink, width=6)
    elif kind == "kids":
        draw.ellipse((cx-width*.09, height*.18, cx+width*.09, height*.30), fill=soft, outline=ink, width=3)
        draw.polygon([(cx, height*.31), (width*.28, height*.68), (width*.72, height*.68)], fill=soft, outline=ink)
    elif kind == "men":
        draw.polygon([(cx-width*.11,height*.22),(cx+width*.11,height*.22),(width*.72,height*.42),(width*.63,height*.72),(width*.37,height*.72),(width*.28,height*.42)], fill=soft, outline=ink)
        draw.line((cx,height*.22,cx,height*.72), fill=ink, width=3)
    else:  # women/sports/outlet
        draw.polygon([(cx-width*.10,height*.20),(cx+width*.10,height*.20),(width*.70,height*.70),(width*.30,height*.70)], fill=soft, outline=ink)
        if kind == "sports":
            draw.line((width*.32,height*.48,width*.68,height*.48), fill=ink, width=4)

    # واترمارک کوچک QA؛ برای جلوگیری از اشتباه با عکس واقعی فروشگاه مرجع.
    draw.rounded_rectangle((width*.04, height*.04, width*.22, height*.10), radius=8, fill=(255,255,255), outline=(180,180,180))
    draw.text((width*.075, height*.052), "QA", fill=(40,40,40))

    buf = BytesIO()
    image.save(buf, "JPEG", quality=88, optimize=True)
    return SimpleUploadedFile(filename, buf.getvalue(), content_type="image/jpeg")


def _product_kind(product: Product) -> str:
    node = product.category
    while node and node.parent_id:
        node = node.parent
    return getattr(node, "slug", "women") or "women"


class Command(FashionSeedCommand):
    help = "ساخت فروشگاه QA محلی پر‌داده با ساختار فروشگاهی نزدیک به KianStock؛ فقط DEBUG."

    def add_arguments(self, parser):
        parser.add_argument("--owner-username", required=True)
        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_kianstock_qa_demo فقط در DEBUG=True قابل اجراست.")
        try:
            owner = User.objects.get(username=options["owner_username"])
        except User.DoesNotExist as exc:
            raise CommandError("owner-username باید یک کاربر موجود باشد؛ کاربر ناامن خودکار ساخته نمی‌شود.") from exc
        if options["reset"]:
            self._reset(options["owner_username"])

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
            image_count = self._seed_product_images(products)
            collections = self._seed_collections(store, products)
            hero_count = self._seed_hero_slides(store)
            banner_count = self._seed_banners(store)
            story_count = self._seed_story_rail(store, categories)
            menu_count = self._seed_navigation(store, categories)
            social_count = self._seed_social_links(store)
            page_count = self._seed_content_pages(store)
            self._seed_builder(store, owner, categories, brands, collections)

        self.stdout.write(self.style.SUCCESS(
            "seed_kianstock_qa_demo با موفقیت اجرا شد:\n"
            f"  Store: {store.slug}\n"
            f"  Category: {Category.objects.filter(store=store).count()}\n"
            f"  Product: {Product.objects.filter(store=store).count()}\n"
            f"  Brand: {Brand.objects.filter(store=store).count()}\n"
            f"  Variant: {variant_stats['total']} روی {variant_stats['products']} کالا\n"
            f"  ProductImage: {image_count}\n"
            f"  Collections: {len(collections)}\n"
            f"  Hero/Banner/Story: {hero_count}/{banner_count}/{story_count}\n"
            f"  Menu/Social/Page: {menu_count}/{social_count}/{page_count}\n"
            "  Note: تصاویر و متن‌های بلند سایت مرجع کپی نشده‌اند؛ تصاویر QA محلی synthetic هستند."
        ))

    @transaction.atomic
    def _reset(self, owner_username):
        existing = Store.objects.filter(slug=STORE_SLUG).first()
        if not existing:
            self.stdout.write("  --reset: فروشگاه QA وجود نداشت.")
            return
        # ترتیب حذف باید PROTECTها را از پایینِ گراف باز کند.
        # Product.category -> PROTECT، پس محصولات قبل از Category/Store حذف می‌شوند.
        Product.objects.filter(store=existing).delete()

        # MenuItem.parent و MenuItem.menu هر دو PROTECT هستند. مدل حداکثر دو سطح
        # (والد + فرزند) را مجاز می‌کند، بنابراین ابتدا فرزندان و سپس والدها
        # حذف می‌شوند تا هیچ parentِ محافظت‌شده‌ای باقی نماند.
        MenuItem.objects.filter(
            menu__store=existing,
            parent__isnull=False,
        ).delete()
        MenuItem.objects.filter(
            menu__store=existing,
            parent__isnull=True,
        ).delete()

        existing.delete()
        self.stdout.write("  --reset: فقط kianstock-qa حذف شد.")

    def _seed_store(self):
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
        if not created:
            store.name = STORE_NAME
            store.status = Store.Status.ACTIVE
            store.admin_subdomain = normalize_admin_subdomain(STORE_ADMIN_SUBDOMAIN)
            store.onboarding_stage = Store.OnboardingStage.DONE
            store.onboarding_completed_at = store.onboarding_completed_at or timezone.now()
            store.save()
        self._log("Store", int(created))
        return store

    def _seed_shop_settings(self, store):
        shop = ShopSettings.provision_for(store)
        shop.name = STORE_NAME
        shop.tagline = "K I A N S T O C K · QA LOCAL"
        shop.description = "نسخه محلی QA برای سنجش چیدمان و رفتار Storefront Builder با کاتالوگ پرتراکم استوک."
        shop.contact_phone = PUBLIC_PHONE
        shop.contact_email = "qa-kianstock@example.com"
        shop.contact_address = ""
        shop.gift_wrap_available = True
        shop.gift_wrap_price = Decimal("45000")
        shop.save()
        self._log("ShopSettings", 0, note="هویت QA + تماس عمومی + کادوپیچی")

    def _seed_footer_settings(self, store):
        footer = FooterSettings.provision_for(store)
        footer.is_enabled = True
        footer.show_branding = True
        footer.show_logo = True
        footer.description = "فروشگاه استوک چنددسته‌ای — نسخه QA محلی برای آزمون قالب‌ها."
        footer.show_contact = True
        footer.address = ""
        footer.phone = PUBLIC_PHONE
        footer.secondary_phone = KIDS_PHONE
        footer.email = "qa-kianstock@example.com"
        footer.working_hours = SUPPORT_HOURS
        footer.show_navigation = True
        footer.show_social_links = True
        footer.show_newsletter = True
        footer.newsletter_title = "عضویت در باشگاه مشتریان"
        footer.newsletter_description = "شماره موبایل خود را برای دریافت پیشنهادهای QA وارد کنید."
        footer.copyright_text = "KIAN STOCK · LOCAL QA DATASET"
        footer.save()
        self._log("FooterSettings", 0)

    def _seed_vendor(self, store):
        vendor, created = Vendor.objects.get_or_create(
            store=store, slug="kianstock-qa-vendor",
            defaults={"name": "کیان استوک", "is_active": True},
        )
        self._log("Vendor", int(created))
        return vendor

    def _seed_categories(self, store):
        result, created_count = {}, 0
        for top_order, top in enumerate(TOP_CATEGORIES):
            parent, created = Category.objects.get_or_create(
                store=store, slug=top["slug"],
                defaults={"name": top["name"], "icon": top["icon"], "order": top_order, "is_active": True},
            )
            created_count += int(created)
            result[top["slug"]] = parent
            if not parent.image:
                parent.image.save(
                    f"{top['slug']}.jpg",
                    _jpeg_upload(f"{top['slug']}.jpg", width=900, height=650, kind=top["slug"], index=top_order),
                    save=True,
                )
            for child_order, (name, slug) in enumerate(top["children"]):
                child, child_created = Category.objects.get_or_create(
                    store=store, slug=slug,
                    defaults={"name": name, "parent": parent, "order": child_order, "is_active": True},
                )
                created_count += int(child_created)
                result[slug] = child
        self._log("Category", created_count)
        return result

    def _seed_brands(self, store):
        result, created_count = {}, 0
        for order, (name, slug) in enumerate(BRANDS):
            brand, created = Brand.objects.get_or_create(
                store=store, slug=slug,
                defaults={"name": name, "name_en": name, "sort_order": order, "is_active": True},
            )
            created_count += int(created)
            result[slug] = brand
        self._log("Brand", created_count)
        return result

    def _seed_products(self, store, vendor, categories, brands):
        products, created_count = [], 0
        for index, (collection_slug, category_slug, brand_slug, name, current_price, regular_price) in enumerate(PRODUCTS, start=1):
            sku = f"KSQA-{index:04d}"
            slug = slugify(f"ksqa-{index}-{name}", allow_unicode=True)[:230]
            base_price = Decimal(str(regular_price or current_price))
            if regular_price:
                pct = int(round((1 - (current_price / regular_price)) * 100))
                pct = max(1, min(90, pct))
            else:
                pct = 0
            tag = Product.Tag.SALE if collection_slug == "sale" else (Product.Tag.NEW if collection_slug == "newest" else "")
            stock = 0 if index % 19 == 0 else (2 if index % 11 == 0 else 12 + index % 17)
            product, created = Product.objects.get_or_create(
                store=store, sku=sku,
                defaults={
                    "vendor": vendor, "category": categories[category_slug], "brand": brands.get(brand_slug),
                    "name": name, "slug": slug,
                    "description": (
                        f"{name}. توضیح کوتاه QA مستقل برای آزمون صفحه محصول، گالری، تنوع، قیمت، "
                        "سبد خرید و ریسپانسیو؛ متن توضیح سایت مرجع کپی نشده است."
                    ),
                    "price": base_price, "discount_percent": pct, "stock": stock,
                    "status": Product.Status.ACTIVE, "visibility": Product.Visibility.PUBLIC,
                    "tag": tag, "unit": Product.Unit.PIECE,
                    "rating": Decimal(str(4 + (index % 10) / 10)).quantize(Decimal("0.01")),
                    "reviews_count": 3 + (index * 7) % 86,
                    "sold_count": 5 + (index * 13) % 230,
                    "views_count": 100 + (index * 47) % 4000,
                },
            )
            created_count += int(created)
            products.append(product)
        self._log("Product", created_count)
        return products

    def _seed_variants(self, products):
        total = 0
        product_count = 0
        for index, product in enumerate(products, start=1):
            if product.variants.exists():
                total += product.variants.count()
                product_count += 1
                continue
            kind = _product_kind(product)
            values = []
            attribute = "سایز"
            if kind == "sneakers":
                values = ["36", "37", "38", "39", "40", "41", "42"]
            elif kind == "footwear":
                values = ["37", "38", "39", "40", "41"]
            elif kind == "kids":
                values = ["4 سال", "6 سال", "8 سال", "10 سال", "12 سال"]
            elif kind in {"women", "men", "sports", "outlet"}:
                # عمداً mix: بخشی سایز و بخشی رنگ، تا QA هم variant selector
                # و هم variant-driven image switching را با داده‌ی واقعی مدل بسنجد.
                if index % 2 == 0:
                    attribute = "رنگ"
                    values = ["مشکی", "کرم", "قهوه‌ای"]
                else:
                    values = ["S", "M", "L", "XL"]
            elif kind == "accessories" and index % 2 == 0:
                attribute = "رنگ"
                values = ["مشکی", "کرم", "قهوه‌ای"]
            if not values:
                continue
            for v_index, value in enumerate(values):
                stock = 0 if (v_index == 0 and index % 5 == 0) else 3 + (index + v_index) % 9
                hex_value = {"مشکی":"#111111","کرم":"#E8DDC8","قهوه‌ای":"#6B4F3A"}.get(value, "")
                create_variant(product, attribute=attribute, value=value, stock=stock, value_hex=hex_value)
                total += 1
            product_count += 1
            product.product_type = Product.ProductType.VARIABLE
            product.save(update_fields=["product_type", "updated_at"])
        self._log("ProductVariant", total)
        return {"total": total, "products": product_count}

    def _seed_product_images(self, products):
        total = 0
        for index, product in enumerate(products, start=1):
            kind = _product_kind(product)
            if not product.images.exists():
                for shot in range(2):
                    img = add_product_image(
                        product,
                        _jpeg_upload(f"{product.slug}-{shot}.jpg", width=900, height=1200, kind=kind, index=index + shot*101),
                        alt=product.name,
                    )
                    total += 1
                    # برای بخشی از رنگ‌ها، عکس را واقعاً به variant مربوط کن.
                    if shot == 1:
                        color_variant = product.variants.filter(attribute="رنگ").first()
                        if color_variant:
                            set_image_variant(img, color_variant)
            else:
                total += product.images.count()
        self._log("ProductImage", total)
        return total

    def _seed_collections(self, store, products):
        by_group = {slug: [] for slug, _ in COLLECTIONS}
        for product, row in zip(products, PRODUCTS):
            by_group[row[0]].append(product)
        collections = []
        for order, (slug, title) in enumerate(COLLECTIONS):
            collection, created = MerchantCollection.objects.get_or_create(
                store=store, slug=f"ks-{slug}",
                defaults={"name": title, "is_active": True},
            )
            if created:
                MerchantCollectionItem.objects.bulk_create([
                    MerchantCollectionItem(collection=collection, product=p, order=i)
                    for i, p in enumerate(by_group[slug])
                ])
            collections.append(collection)
        self._log("MerchantCollection", len(collections))
        return collections

    def _seed_hero_slides(self, store):
        slides = [
            ("استوک اورجینال؛ انتخاب‌های تازه", "از پوشاک تا کتونی و عطر", "men"),
            ("جدیدترین‌های فروشگاه", "هر روز کالاهای تازه برای بررسی کارت و اسلایدر", "women"),
            ("کتونی و اکسسوری", "چیدمان پرتراکم برای QA دسکتاپ و موبایل", "sneakers"),
        ]
        count = 0
        for order, (title, subtitle, kind) in enumerate(slides):
            if HeroSlide.objects.filter(store=store, title=title).exists():
                continue
            obj = HeroSlide(store=store, title=title, subtitle=subtitle, display_order=order, is_active=True, show_button=False, destination_type=DestinationType.NONE)
            obj.desktop_image = _jpeg_upload(f"ks-hero-{order}.jpg", width=1600, height=620, kind=kind, index=order+200)
            obj.mobile_image = _jpeg_upload(f"ks-hero-m-{order}.jpg", width=700, height=900, kind=kind, index=order+210)
            obj.save()
            count += 1
        self._log("HeroSlide", count)
        return count

    def _seed_banners(self, store):
        rows = [
            ("پوشاک زنانه", "women"), ("پوشاک مردانه", "men"),
            ("عطر و ادکلن", "perfume"), ("عینک و اکسسوری", "sunglasses"),
        ]
        count = 0
        for order, (title, kind) in enumerate(rows):
            if PromotionalBanner.objects.filter(store=store, title=title).exists():
                continue
            obj = PromotionalBanner(store=store, title=title, display_order=order, is_active=True, show_button=False, destination_type=DestinationType.NONE)
            obj.desktop_image = _jpeg_upload(f"ks-banner-{order}.jpg", width=1200, height=420, kind=kind, index=order+300)
            obj.save()
            count += 1
        self._log("PromotionalBanner", count)
        return count

    def _seed_story_rail(self, store, categories):
        # معادل چهار شعبه/کانال اجتماعی در بخش پایین صفحه؛ تصاویر QA جایگزین‌اند.
        rows = [
            ("kian.stock", "women"), ("kian.stock1", "kids"),
            ("kianstockshoes", "sneakers"), ("kiano.optic", "sunglasses"),
        ]
        count = 0
        for order, (title, category_slug) in enumerate(rows):
            if StoryRailItem.objects.filter(store=store, title=title).exists():
                continue
            item = StoryRailItem(
                store=store, title=title, is_active=True, display_order=order,
                destination_type=DestinationType.CATEGORY,
                destination_category=categories[category_slug],
            )
            item.image = _jpeg_upload(f"ks-story-{order}.jpg", width=500, height=500, kind=category_slug, index=400+order)
            item.save()
            count += 1
        self._log("StoryRailItem", count)
        return count

    def _seed_navigation(self, store, categories):
        # منوی فروشگاه: مطابق ترتیب عمومی سایت مرجع + زیرمنوهای واقعی از درخت QA.
        header, _ = Menu.objects.get_or_create(store=store, location=Menu.Location.HEADER, defaults={"title":"منو فروشگاه", "is_active":True})
        count = 0
        order = 0
        quick = [("جدیدترین ها", "newest"), ("تخفیفات فروشگاه", "sale")]
        for title, collection_key in quick:
            col = MerchantCollection.objects.get(store=store, slug=f"ks-{collection_key}")
            _, created = MenuItem.objects.get_or_create(menu=header, title=title, parent=None, defaults={"display_order":order,"is_active":True,"destination_type":DestinationType.COLLECTION,"destination_collection":col})
            count += int(created); order += 1
        for top in TOP_CATEGORIES:
            parent_cat = categories[top["slug"]]
            item, created = MenuItem.objects.get_or_create(menu=header, title=top["name"], parent=None, defaults={"display_order":order,"is_active":True,"destination_type":DestinationType.CATEGORY,"destination_category":parent_cat})
            count += int(created); order += 1
            # چند فرزند اول برای mega/dropdown واقعی
            for c_order, (child_name, child_slug) in enumerate(top["children"][:6]):
                _, c_created = MenuItem.objects.get_or_create(menu=header, title=child_name, parent=item, defaults={"display_order":c_order,"is_active":True,"destination_type":DestinationType.CATEGORY,"destination_category":categories[child_slug]})
                count += int(c_created)

        # فوتر سه‌ستونه با صفحات داخلی
        for loc, title in [(Menu.Location.FOOTER_1,"دسترسی سریع"),(Menu.Location.FOOTER_2,"خدمات مشتریان"),(Menu.Location.FOOTER_3,"دسته‌بندی‌ها")]:
            Menu.objects.get_or_create(store=store, location=loc, defaults={"title":title,"is_active":True})
        self._log("MenuItem", count)
        return count

    def _seed_social_links(self, store):
        handles = ["kian.stock", "kian.stock1", "kianstockshoes", "kiano.optic"]
        count = 0
        for order, handle in enumerate(handles):
            _, created = SocialLink.objects.get_or_create(
                store=store, title=handle,
                defaults={
                    "platform": SocialLink.Platform.INSTAGRAM,
                    "url": f"https://instagram.com/{handle}", "display_order":order,
                    "is_active":True, "show_in_header":False, "show_in_footer":True,
                },
            )
            count += int(created)
        self._log("SocialLink", count)
        return count

    def _seed_content_pages(self, store):
        # عناوین/ساختار صفحات مشابه مرجع؛ متن‌ها عمداً مستقل و کوتاه‌اند.
        rows = [
            ("تماس با ما","contact-us", f"پشتیبانی عمومی: {PUBLIC_PHONE} | بچگانه: {KIDS_PHONE} | عطر: {PERFUME_PHONE} | عینک: {GLASSES_PHONE} | {SUPPORT_HOURS}"),
            ("درباره ما","about-us", "این صفحه فقط برای QA محلی ساخته شده تا فوتر، ناوبری و صفحه محتوایی تست شوند."),
            ("سئوالات متداول","faq", "پرسش‌های آزمایشی درباره ارسال، اصالت کالا، سایزبندی و مرجوعی."),
            ("باشگاه مشتریان","customer-club", "صفحه QA باشگاه مشتریان برای بررسی ساختار محتوایی و CTA؛ جزئیات برنامه واقعی کپی نشده است."),
            ("مرجوعی کالا","returns", "متن QA برای بررسی صفحه قوانین مرجوعی. سیاست واقعی سایت مرجع در این داده کپی نشده است."),
            ("راهنمای خرید","buying-guide", "راهنمای کوتاه QA برای اندازه، انتخاب محصول و ثبت سفارش."),
        ]
        count = 0
        now = timezone.now()
        pages = []
        for order, (title, slug, body) in enumerate(rows):
            page, created = ContentPage.objects.get_or_create(
                store=store, slug=slug,
                defaults={"title":title,"body":body,"summary":body[:250],"status":ContentPage.Status.PUBLISHED,"published_at":now,"show_in_footer":True,"footer_column":ContentPage.FooterColumn.QUICK_ACCESS if order < 3 else ContentPage.FooterColumn.CUSTOMER_SERVICE,"display_order":order},
            )
            pages.append(page); count += int(created)

        # ContentPage مقصدِ MenuItem نیست؛ صفحات منتشرشده از context processor
        # به‌صورت داده‌محور در header/footer رندر می‌شوند. دو منوی footer را با
        # مقصدهای معتبرِ collection/category پر می‌کنیم تا هیچ لینک مرده‌ای نباشد.
        quick_menu = Menu.objects.get(store=store, location=Menu.Location.FOOTER_1)
        quick_collections = [("جدیدترین ها", "newest"), ("تخفیفات فروشگاه", "sale"), ("کتونی اورجینال", "sneakers")]
        for order, (title, key) in enumerate(quick_collections):
            collection = MerchantCollection.objects.get(store=store, slug=f"ks-{key}")
            MenuItem.objects.get_or_create(
                menu=quick_menu, title=title, parent=None,
                defaults={"display_order": order, "is_active": True,
                          "destination_type": DestinationType.COLLECTION,
                          "destination_collection": collection},
            )

        service_menu = Menu.objects.get(store=store, location=Menu.Location.FOOTER_2)
        for order, top in enumerate(TOP_CATEGORIES[:4]):
            cat = Category.objects.get(store=store, slug=top["slug"])
            MenuItem.objects.get_or_create(
                menu=service_menu, title=cat.name, parent=None,
                defaults={"display_order": order, "is_active": True,
                          "destination_type": DestinationType.CATEGORY,
                          "destination_category": cat},
            )

        cat_menu = Menu.objects.get(store=store, location=Menu.Location.FOOTER_3)
        for order, top in enumerate(TOP_CATEGORIES[:6]):
            cat = Category.objects.get(store=store, slug=top["slug"])
            MenuItem.objects.get_or_create(
                menu=cat_menu, title=cat.name, parent=None,
                defaults={"display_order": order, "is_active": True,
                          "destination_type": DestinationType.CATEGORY,
                          "destination_category": cat},
            )
        self._log("ContentPage", count)
        return count

    def _seed_builder(self, store, owner, categories, brands, collections):
        layout = layout_service.get_or_create_layout(store)
        marker_title = "تخفیفات شگفت انگیز"
        if layout.published_version_id and not layout.draft_version_id:
            has_marker = layout.published_version.sections.filter(section_key="product_section", settings__title=marker_title).exists()
            if has_marker:
                self._log("StorefrontLayoutVersion", 0, note="چیدمان KianStock-QA از قبل منتشر است")
                return

        draft = layout_service.get_or_create_draft(store, user=owner)
        appearance = layout_service.validate_appearance_config({
            "palette_slug": None,
            "color_overrides": {
                "primary":"#111111", "secondary":"#3A3A3A", "accent":"#D71920",
                "background":"#F7F7F7", "surface":"#FFFFFF", "text":"#171717",
                "muted":"#737373", "border":"#E5E5E5",
            },
            "radius": 10, "button_radius": 8, "density":"compact", "motion":"subtle",
            "type_scale":"normal", "button_style":"filled", "image_fit":"cover", "image_hover":"zoom",
        })
        draft.appearance_config = appearance
        draft.header_config = layout_service.validate_header_config({
            "show_search":True, "show_account":True, "show_cart":True, "show_wishlist":True,
            "sticky":True, "announcement_enabled":True,
            "announcement_text":"ارسال سفارش‌ها و پاسخگویی پشتیبانی در ساعات اعلام‌شده · QA LOCAL",
        })
        draft.footer_config = layout_service.validate_footer_config({
            "show_about":True,"show_contact":True,"show_quick_links":True,"show_categories":True,
            "show_social":True,"show_trust_badges":False,"show_payment_logos":False,
            "show_newsletter":True,"show_copyright":True,
        })
        draft.save(update_fields=["appearance_config","header_config","footer_config","updated_at"])

        # هومپیجِ پرتراکمِ QA این فروشگاه کاملاً دستی/صریح ساخته می‌شود
        # (نه از پیش‌فرضِ یک Preset) — همیشه صفحه‌ی اصلیِ Draft را قبل از
        # ساختِ ردیف‌های زیر خالی می‌کند.
        draft.sections.all().delete()

        order = 0
        def add(key, raw=None):
            nonlocal order
            definition = section_registry.get_definition(key)
            settings_data = definition.validate_settings(raw if raw is not None else definition.default_settings())
            StorefrontSection.objects.create(version=draft, section_key=key, order=order, is_active=True, settings=settings_data)
            order += 1

        add("hero_banner", {"autoplay": True, "interval_ms": 5000, "loop": True, "show_arrows": True, "show_dots": True})
        add("multi_banner", {})
        add("category_grid", {"title":"دسته بندی محصولات", "display_mode":"grid", "category_ids":[categories[t["slug"]].id for t in TOP_CATEGORIES]})
        collection_map = {c.slug.removeprefix("ks-"): c for c in collections}
        for slug, title in COLLECTIONS:
            add("product_section", {
                "data_source":"collection", "source_id":collection_map[slug].id,
                "item_limit":10, "display_mode":"carousel", "show_view_all":True,
                "title":title, "subtitle":"", "card_mode":"default",
                "responsive":{"desktop_columns":5,"tablet_columns":3,"mobile_columns":2},
            })
        add("brand_carousel", {"title":"برندهای موجود", "display_mode":"carousel", "show_view_all":False, "brand_ids":[b.id for b in list(brands.values())[:18]]})
        add("story_rail", {})
        add("testimonials", {"title":"رضایت مشتریان — داده QA", "items":[
            {"name":"مشتری QA ۱","role":"خرید آزمایشی","quote":"کارت محصول، قیمت و وضعیت ارسال در این متن فقط برای تست چیدمان بررسی می‌شود."},
            {"name":"مشتری QA ۲","role":"خرید آزمایشی","quote":"این رضایت‌نامه synthetic است و از سایت مرجع کپی نشده است."},
            {"name":"مشتری QA ۳","role":"خرید آزمایشی","quote":"برای تست موبایل، طول متن عمداً متفاوت در نظر گرفته شده است."},
        ]})
        add("faq", {"title":"سئوالات متداول", "items":[
            {"question":"چطور سایز مناسب را انتخاب کنم؟","answer":"این پاسخ QA است؛ از جدول سایز و گزینه‌های محصول برای بررسی رابط استفاده کنید."},
            {"question":"آیا کالاهای ناموجود قابل افزودن هستند؟","answer":"خیر؛ این دیتاست چند وضعیت موجودی برای آزمون کنترل سبد خرید دارد."},
            {"question":"چطور محصولات تخفیف‌دار را پیدا کنم؟","answer":"ردیف تخفیفات شگفت انگیز و کالکشن مربوطه برای همین تست ساخته شده است."},
        ]})
        add("trust_features", {})
        layout_service.publish(store, user=owner)
        self._log("StorefrontLayoutVersion", 0, note="KianStock-QA منتشر شد")
