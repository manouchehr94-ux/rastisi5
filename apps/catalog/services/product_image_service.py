"""سرویس مدیریت گالری تصاویر کالا — آپلود، اعتبارسنجی، تغییر اندازه و بندانگشتی.

قواعد:
- فرمت‌های مجاز: jpg/jpeg/png/webp، حداکثر حجم ۵ مگابایت.
- تصویر اصلی اگر از حد مجاز بزرگ‌تر باشد خودکار کوچک می‌شود (بدون افت کیفیت
  برای تصاویر کوچک‌تر — Pillow.thumbnail فقط در صورت نیاز کوچک می‌کند).
- برای هر تصویر یک نسخه‌ی بندانگشتی هم ساخته می‌شود تا صفحات سریع‌تر باز شوند.
- اولین تصویر هر کالا خودکار کاور می‌شود؛ با حذف کاور، تصویر بعدی (طبق ترتیب)
  خودکار جایگزین می‌شود تا کالای دارای تصویر همیشه یک کاور مشخص داشته باشد.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from django.utils.crypto import get_random_string
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.catalog.models import ProductImage

MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}
EXTENSION_BY_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

MAX_DIMENSION = 2000
THUMBNAIL_DIMENSION = 400


class ProductImageError(Exception):
    """خطای قابل‌نمایش هنگام اعتبارسنجی/پردازش تصویر کالا."""


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def validate_image_file(file) -> None:
    """پسوند، حجم و معتبربودن واقعی فایل را بررسی می‌کند؛ در خطا ProductImageError می‌دهد."""
    ext = _extension(getattr(file, "name", ""))
    if ext not in ALLOWED_EXTENSIONS:
        allowed = "، ".join(sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS))
        raise ProductImageError(f"فرمت تصویر مجاز نیست. فرمت‌های مجاز: {allowed}")

    if file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ProductImageError("حجم تصویر نباید بیشتر از ۵ مگابایت باشد.")

    try:
        file.seek(0)
        with Image.open(file) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductImageError("فایل انتخاب‌شده تصویر معتبری نیست.") from exc
    finally:
        file.seek(0)


def _shrink_to_fit(image: Image.Image, max_dimension: int) -> Image.Image:
    resized = image.copy()
    resized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return resized


def _encode(image: Image.Image, fmt: str) -> bytes:
    buffer = BytesIO()
    save_kwargs = {"quality": 85, "optimize": True} if fmt in ("JPEG", "WEBP") else {}
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def _load_normalized_image(file):
    file.seek(0)
    opened = Image.open(file)
    opened.load()

    fmt = (opened.format or "JPEG").upper()
    if fmt not in ALLOWED_PIL_FORMATS:
        fmt = "JPEG"

    pil_image = ImageOps.exif_transpose(opened) or opened
    if fmt == "JPEG" and pil_image.mode not in ("RGB", "L"):
        pil_image = pil_image.convert("RGB")
    elif fmt in ("PNG", "WEBP") and pil_image.mode not in ("RGB", "RGBA"):
        pil_image = pil_image.convert("RGBA")

    return pil_image, fmt


def add_product_image(product, file, *, alt: str = "") -> ProductImage:
    """تصویر را اعتبارسنجی، در صورت نیاز کوچک، و همراه بندانگشتی برای کالا ثبت می‌کند."""
    validate_image_file(file)
    pil_image, fmt = _load_normalized_image(file)

    main_image = _shrink_to_fit(pil_image, MAX_DIMENSION)
    thumb_image = _shrink_to_fit(pil_image, THUMBNAIL_DIMENSION)
    ext = EXTENSION_BY_FORMAT[fmt]
    base_name = f"{product.slug}-{get_random_string(10)}"

    next_order = product.images.count()
    instance = ProductImage(product=product, alt=(alt or "").strip(), order=next_order, is_cover=next_order == 0)
    instance.image.save(f"{base_name}{ext}", ContentFile(_encode(main_image, fmt)), save=False)
    instance.thumbnail.save(f"{base_name}-thumb{ext}", ContentFile(_encode(thumb_image, fmt)), save=False)
    instance.save()
    return instance


def delete_product_image(image: ProductImage) -> None:
    """تصویر و فایل‌های آن را حذف می‌کند؛ اگر کاور بود، تصویر بعدی خودکار کاور می‌شود."""
    product = image.product
    was_cover = image.is_cover

    if image.image:
        image.image.delete(save=False)
    if image.thumbnail:
        image.thumbnail.delete(save=False)
    image.delete()

    if was_cover:
        next_image = product.images.order_by("order", "id").first()
        if next_image is not None:
            next_image.is_cover = True
            next_image.save(update_fields=["is_cover"])


def set_cover_image(product, image_id) -> ProductImage:
    """دقیقاً یک تصویر کالا را کاور می‌کند؛ بقیه خودکار غیرکاور می‌شوند."""
    image = product.images.filter(pk=image_id).first()
    if image is None:
        raise ProductImageError("تصویر مورد نظر یافت نشد.")

    product.images.exclude(pk=image.pk).filter(is_cover=True).update(is_cover=False)
    if not image.is_cover:
        image.is_cover = True
        image.save(update_fields=["is_cover"])
    return image


def move_product_image(image: ProductImage, direction: str) -> None:
    """ترتیب نمایش تصویر را با همسایه‌ی بالا/پایین آن جابه‌جا می‌کند."""
    ordered = list(image.product.images.order_by("order", "id"))
    index = next((i for i, item in enumerate(ordered) if item.pk == image.pk), None)
    if index is None:
        return

    if direction == "up" and index > 0:
        neighbor = ordered[index - 1]
    elif direction == "down" and index < len(ordered) - 1:
        neighbor = ordered[index + 1]
    else:
        return

    image.order, neighbor.order = neighbor.order, image.order
    ProductImage.objects.bulk_update([image, neighbor], ["order"])


def update_image_alt(image: ProductImage, alt: str) -> ProductImage:
    image.alt = (alt or "").strip()
    image.save(update_fields=["alt"])
    return image
