"""لایه‌ی سرویسِ برچسبِ کالا — دقیقاً همان الگویِ CustomerTag
(``apps.customers.models.CustomerTag``): ``code`` در محدوده‌ی Store یکتاست،
حذفِ فیزیکی وقتی به کالایی متصل است مجاز نیست، به‌جای آن آرشیو می‌شود."""

from django.utils.text import slugify

from apps.catalog.models import ProductTag
from apps.core.utils import normalization_key


def get_or_create_tags(store, names: list[str]) -> list[ProductTag]:
    """فهرستی از نام‌های برچسبِ عادی را به رکوردهای ProductTag تبدیل می‌کند —
    برچسبِ موجود (با هر بزرگی/کوچکی حروف یا فاصله‌ی مشابه) دوباره ساخته
    نمی‌شود؛ اگر قبلاً آرشیو شده بود، دوباره فعال می‌شود. همیشه
    ``purpose=GENERAL`` است — برایِ «گروهِ دوم» از
    ``get_or_create_collection_tag`` استفاده کنید."""
    tags = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        code = slugify(name, allow_unicode=True) or normalization_key(name)
        tag = ProductTag.objects.filter(store=store, code=code).first()
        if tag is None:
            tag = ProductTag.objects.create(store=store, code=code, name=name, purpose=ProductTag.Purpose.GENERAL)
        elif not tag.is_active:
            tag.is_active = True
            tag.save(update_fields=["is_active", "updated_at"])
        tags.append(tag)
    return tags


def suggest_tags(store, query: str = "", *, limit: int = 20):
    """پیشنهادِ برچسب‌هایِ عادیِ موجود برایِ تکمیلِ خودکار در فرمِ کالا —
    عمداً «گروهِ دوم»هایِ Purpose.COLLECTION را نشان نمی‌دهد تا دو مفهومِ
    جداگانه (برچسبِ آزاد در برابرِ مجموعه‌ی فروش) با هم قاطی نشوند."""
    qs = ProductTag.objects.filter(store=store, is_active=True, purpose=ProductTag.Purpose.GENERAL)
    if query:
        qs = qs.filter(name__icontains=query)
    return qs.order_by("name")[:limit]


#: مقادیرِ پیش‌فرضِ «گروهِ دوم» — دقیقاً همان فهرستِ تأییدشده در پلنِ اجرا
#: (مرحله‌ی ۵)، برایِ اولین باری که فروشگاه به این فیلد نیاز پیدا می‌کند
#: به‌صورتِ تنبل (lazy) و ایمن (idempotent) ساخته می‌شوند — نه در زمانِ
#: ساختِ Store، تا هیچ فروشگاهِ قدیمی‌ای مجبور به مایگریشنِ داده نشود.
DEFAULT_COLLECTION_NAMES = [
    "پیشنهاد ویژه", "جدیدترین‌ها", "پرفروش‌ها", "تخفیف‌دارها", "انتخاب سردبیر", "مناسب هدیه",
]


def ensure_default_collections(store) -> None:
    """اگر این Store هنوز هیچ «گروهِ دوم»ای نداشته باشد، فهرستِ پیش‌فرض را
    می‌سازد — idempotent (فراخوانیِ دوباره چیزی تکراری نمی‌سازد)."""
    if ProductTag.objects.filter(store=store, purpose=ProductTag.Purpose.COLLECTION).exists():
        return
    for name in DEFAULT_COLLECTION_NAMES:
        code = slugify(name, allow_unicode=True) or normalization_key(name)
        ProductTag.objects.get_or_create(
            store=store, code=code, defaults={"name": name, "purpose": ProductTag.Purpose.COLLECTION},
        )


def collection_tags(store):
    """فهرستِ «گروه‌هایِ دوم» (مجموعه‌هایِ فروش) فعالِ این Store."""
    return ProductTag.objects.filter(
        store=store, is_active=True, purpose=ProductTag.Purpose.COLLECTION,
    ).order_by("name")


def get_or_create_collection_tag(store, name: str) -> ProductTag:
    """دقیقاً مثلِ ``get_or_create_tags`` اما برایِ یک «گروهِ دوم» تکی، با
    ``purpose=COLLECTION``."""
    name = name.strip()
    code = slugify(name, allow_unicode=True) or normalization_key(name)
    tag = ProductTag.objects.filter(store=store, code=code).first()
    if tag is None:
        tag = ProductTag.objects.create(store=store, code=code, name=name, purpose=ProductTag.Purpose.COLLECTION)
    else:
        updates = []
        if not tag.is_active:
            tag.is_active = True
            updates.append("is_active")
        if tag.purpose != ProductTag.Purpose.COLLECTION:
            tag.purpose = ProductTag.Purpose.COLLECTION
            updates.append("purpose")
        if updates:
            tag.save(update_fields=[*updates, "updated_at"])
    return tag


def archive_tag(tag: ProductTag) -> ProductTag:
    if tag.is_active:
        tag.is_active = False
        tag.save(update_fields=["is_active", "updated_at"])
    return tag
