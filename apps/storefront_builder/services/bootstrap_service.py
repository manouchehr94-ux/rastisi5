"""مهاجرت غیرمخرب فروشگاه‌های موجود — تولید یک Draft اولیه که دقیقاً منعکس‌کننده‌ی
صفحه اصلی قدیمی (hard-coded) هر فروشگاه است، نه یک بوم خالی.

طبق الزام صریح («هیچ فروشگاهی نباید صفحه اصلی خالی دریافت کند») و بخش ۲۳
گزارش ممیزی: این Draft **منتشر نمی‌شود** — پرچم
``StorefrontLayout.uses_visual_storefront_layout`` فقط با اولین Publish
دستیِ تاجر True می‌شود (در ``layout_service.publish``). تا آن لحظه،
``apps.catalog.views.home`` بدون تغییر از مسیر قدیمی رندر می‌کند.

منطق تشخیص بخش‌ها عمداً از سرویس‌های موجود catalog استفاده می‌کند
(``storefront_listing_products``) — نه بازنویسی قوانین «قابل‌مشاهده بودن».
"""

from __future__ import annotations

from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.content.models import HeroSlide, PromotionalBanner

from ..models import StorefrontLayoutVersion, StorefrontSection


def build_bootstrap_sections(store) -> list[dict]:
    """فهرست بخش‌های اولیه — دقیقاً همان چیزی که در حال حاضر روی صفحه اصلی
    قدیمی این Store رندر می‌شود (بخش ۲.۲ گزارش ممیزی)."""
    sections: list[dict] = []
    order = 0

    if HeroSlide.objects.filter(store=store, is_active=True).exists():
        sections.append({"section_key": "hero_banner", "order": order, "settings": {}})
        order += 1

    if PromotionalBanner.objects.filter(store=store, is_active=True).exists():
        sections.append({"section_key": "multi_banner", "order": order, "settings": {}})
        order += 1

    sections.append({"section_key": "category_grid", "order": order, "settings": {}})
    order += 1

    sections.append({"section_key": "newest_products", "order": order, "settings": {}})
    order += 1

    sections.append({"section_key": "best_sellers", "order": order, "settings": {}})
    order += 1

    if storefront_listing_products(store).filter(discount_percent__gt=0).exists():
        sections.append({"section_key": "discounted_products", "order": order, "settings": {}})
        order += 1

    sections.append({"section_key": "trust_features", "order": order, "settings": {}})
    order += 1

    return sections


def apply_bootstrap_content(version: StorefrontLayoutVersion, store) -> None:
    """بخش‌های اولیه را روی یک نسخه‌ی تازه‌ساخته (بدون بخش) اعمال می‌کند."""
    sections = build_bootstrap_sections(store)
    StorefrontSection.objects.bulk_create([
        StorefrontSection(
            version=version, section_key=s["section_key"],
            order=s["order"], settings=s["settings"],
        )
        for s in sections
    ])
