"""تبدیلِ اختیاریِ «گروه دوم» (``ProductTag(purpose="collection")``) به
``MerchantCollection`` واقعی — فقط با اجرایِ صریحِ دستورِ مدیریتیِ
``migrate_legacy_product_tag_collections``، هرگز خودکار و هرگز داخلِ
مایگریشنِ اسکیمای فاز B.

قوانین:

- ``ProductTag`` مبدأ هرگز حذف/ویرایش نمی‌شود — «گروه دوم» در فرمِ کالا
  دقیقاً همان‌طور که هست کار می‌کند.
- Idempotent: اجرایِ دوباره (چه dry-run چه apply) هرگز کالکشنِ تکراری
  نمی‌سازد — ردیابی از طریقِ ``MerchantCollection.source_legacy_product_tag``
  (همان الگویِ ``Category.source_template_category``)، نه حدسِ اسلاگ/نام.
- هرگز رابطه‌ی بین‌فروشگاهی نمی‌سازد — کوئریِ کالاها همیشه با
  ``store=tag.store`` صریح فیلتر می‌شود.
- ترتیبِ کالاها در کالکشنِ تازه‌ساخته بر اساسِ ``Product.pk`` است — تنها
  ترتیبِ deterministic موجود، چون ``Product.tags`` یک M2M ساده بدونِ فیلدِ
  order است (یافته‌ی ممیزیِ فاز A، بخش ۶).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import MerchantCollection, MerchantCollectionItem, Product, ProductTag
from apps.catalog.services.collection_service import _unique_slug

Status = Literal["created", "reused", "skipped", "conflicted"]


@dataclass
class TagConversionResult:
    tag_id: int
    tag_name: str
    store_id: int
    status: Status
    collection_id: int | None = None
    items_created: int = 0
    items_already_present: int = 0
    detail: str = ""


@dataclass
class LegacyConversionReport:
    dry_run: bool
    results: list[TagConversionResult] = field(default_factory=list)

    def _count(self, status: Status) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def created_count(self) -> int:
        return self._count("created")

    @property
    def reused_count(self) -> int:
        return self._count("reused")

    @property
    def skipped_count(self) -> int:
        return self._count("skipped")

    @property
    def conflicted_count(self) -> int:
        return self._count("conflicted")

    @property
    def total_items_created(self) -> int:
        return sum(r.items_created for r in self.results)


def _base_slug_for_tag(tag: ProductTag) -> str:
    return slugify(tag.name, allow_unicode=True).strip("-") or f"collection-{tag.pk}"


def _ordered_product_ids_for_tag(tag: ProductTag) -> list[int]:
    return list(
        Product.objects.filter(store=tag.store, tags=tag).order_by("pk").values_list("pk", flat=True)
    )


def _convert_one_tag(tag: ProductTag, *, apply_changes: bool) -> TagConversionResult:
    product_ids = _ordered_product_ids_for_tag(tag)

    already = MerchantCollection.objects.filter(store=tag.store, source_legacy_product_tag=tag).first()
    if already is not None:
        collection = already
        status: Status = "reused"
        detail = f"قبلاً به کالکشن «{already.name}» (pk={already.pk}) تبدیل شده بود"
    elif not product_ids:
        return TagConversionResult(
            tag_id=tag.pk, tag_name=tag.name, store_id=tag.store_id, status="skipped",
            detail="هیچ کالایی به این «گروه دوم» اختصاص ندارد",
        )
    else:
        base_slug = _base_slug_for_tag(tag)
        conflict = MerchantCollection.objects.filter(store=tag.store, slug=base_slug).exclude(
            source_legacy_product_tag=tag
        ).first()
        if conflict is not None:
            status = "conflicted"
            slug = _unique_slug(tag.store, tag.name)
            detail = f"اسلاگ «{base_slug}» قبلاً توسط کالکشنِ دیگری (pk={conflict.pk}) استفاده شده — از «{slug}» استفاده شد"
        else:
            status = "created"
            slug = base_slug
            detail = ""
        if apply_changes:
            collection = MerchantCollection.objects.create(
                store=tag.store, name=tag.name, slug=slug,
                collection_type=MerchantCollection.CollectionType.MANUAL,
                source_legacy_product_tag=tag,
            )
        else:
            collection = None

    result = TagConversionResult(
        tag_id=tag.pk, tag_name=tag.name, store_id=tag.store_id, status=status,
        collection_id=collection.pk if collection else None, detail=detail,
    )

    if apply_changes and collection is not None:
        existing_ids = set(
            MerchantCollectionItem.objects.filter(collection=collection).values_list("product_id", flat=True)
        )
        next_order = MerchantCollectionItem.objects.filter(collection=collection).count()
        new_items = []
        for product_id in product_ids:
            if product_id in existing_ids:
                result.items_already_present += 1
                continue
            new_items.append(MerchantCollectionItem(collection=collection, product_id=product_id, order=next_order))
            next_order += 1
        if new_items:
            MerchantCollectionItem.objects.bulk_create(new_items)
        result.items_created = len(new_items)
    elif status == "reused":
        existing_ids = set(
            MerchantCollectionItem.objects.filter(collection=collection).values_list("product_id", flat=True)
        )
        result.items_created = len([p for p in product_ids if p not in existing_ids])
        result.items_already_present = len(product_ids) - result.items_created
    else:
        result.items_created = len(product_ids)

    return result


def _run(*, store, apply_changes: bool) -> LegacyConversionReport:
    report = LegacyConversionReport(dry_run=not apply_changes)
    tags_qs = ProductTag.objects.filter(purpose=ProductTag.Purpose.COLLECTION, is_active=True)
    if store is not None:
        tags_qs = tags_qs.filter(store=store)
    for tag in tags_qs.select_related("store").order_by("store_id", "name"):
        report.results.append(_convert_one_tag(tag, apply_changes=apply_changes))
    return report


def preview_legacy_conversion(*, store=None) -> LegacyConversionReport:
    """گزارشِ کامل بدونِ نوشتنِ چیزی در دیتابیس — پیش‌فرضِ امنِ دستور."""
    return _run(store=store, apply_changes=False)


@transaction.atomic
def apply_legacy_conversion(*, store=None) -> LegacyConversionReport:
    """اجرایِ واقعی — یک تراکنشِ واحد برایِ کلِ عملیات (تمام Storeها/تگ‌ها با
    هم؛ یا همه اعمال می‌شود یا هیچ‌کدام)."""
    return _run(store=store, apply_changes=True)
