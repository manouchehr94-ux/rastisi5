"""درصدِ تکمیلِ کالا + چک‌لیستِ پیش از انتشار — برایِ نمایشِ راهنما در فرمِ
کالا (Part 9/11 مشخصات). این ماژول هیچ چیزی را مسدود نمی‌کند — فقط
وضعیتِ واقعیِ داده را برایِ مدیرِ فروشگاه خلاصه می‌کند؛ گیتِ واقعیِ انتشار
همچنان ``apps.catalog.services.product_publish_service.validate_product_for_publish``
است.
"""

from dataclasses import dataclass


@dataclass
class ChecklistItem:
    key: str
    label: str
    done: bool
    hint: str = ""


def _has_seo(product) -> bool:
    return bool(product.seo_title) and bool(product.seo_description)


def _has_cover_image(product) -> bool:
    return product.images.exists()


def _has_valid_variant_setup(product) -> bool:
    if product.product_type != product.ProductType.VARIABLE:
        return True
    return product.variants.filter(is_active=True, is_obsolete=False).exists()


def _has_inventory(product) -> bool:
    if product.product_type == product.ProductType.VARIABLE:
        return product.variants.filter(is_active=True, is_obsolete=False, stock__gt=0).exists()
    return product.stock > 0


def build_completion_checklist(product) -> list[ChecklistItem]:
    """چک‌لیستِ کاملِ پیش از انتشار — برایِ نمایش در تبِ «سئو و انتشار»."""
    return [
        ChecklistItem("title", "عنوانِ کالا", bool(product.name)),
        ChecklistItem("category", "دسته‌بندیِ برگ (leaf)", bool(product.category_id)),
        ChecklistItem("cover_image", "تصویرِ اصلی", _has_cover_image(product), "بدونِ تصویر، کالا در فروشگاه جذاب دیده نمی‌شود."),
        ChecklistItem("price", "قیمت", bool(product.price and product.price > 0)),
        ChecklistItem(
            "variants", "پیکربندیِ تنوع", _has_valid_variant_setup(product),
            "کالایِ «دارای تنوع» باید حداقل یک تنوعِ فعال داشته باشد.",
        ),
        ChecklistItem("inventory", "موجودیِ انبار", _has_inventory(product), "بدونِ موجودی، کالا برایِ خرید در دسترس نیست."),
        ChecklistItem("seo", "عنوان/توضیحاتِ سئو", _has_seo(product), "برایِ دیده‌شدنِ بهتر در نتایجِ جست‌وجو."),
        ChecklistItem(
            "status", "وضعیتِ انتشار", product.status == product.Status.ACTIVE,
            "کالا هنوز «فعال» نیست؛ فقط کالاهایِ فعال به مشتری نمایش داده می‌شوند.",
        ),
    ]


def completion_percent(product) -> int:
    """درصدِ تکمیل — از رویِ داده‌ی واقعیِ کالا محاسبه می‌شود، نه هاردکد."""
    items = build_completion_checklist(product)
    if not items:
        return 0
    done = sum(1 for item in items if item.done)
    return round(done * 100 / len(items))
