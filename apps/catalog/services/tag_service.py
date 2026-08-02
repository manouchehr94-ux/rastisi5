"""لایه‌ی سرویسِ برچسبِ کالا — دقیقاً همان الگویِ CustomerTag
(``apps.customers.models.CustomerTag``): ``code`` در محدوده‌ی Store یکتاست،
حذفِ فیزیکی وقتی به کالایی متصل است مجاز نیست، به‌جای آن آرشیو می‌شود."""

from django.utils.text import slugify

from apps.catalog.models import ProductTag
from apps.core.utils import normalization_key


def get_or_create_tags(store, names: list[str]) -> list[ProductTag]:
    """فهرستی از نام‌های برچسب را به رکوردهای ProductTag تبدیل می‌کند —
    برچسبِ موجود (با هر بزرگی/کوچکی حروف یا فاصله‌ی مشابه) دوباره ساخته
    نمی‌شود؛ اگر قبلاً آرشیو شده بود، دوباره فعال می‌شود."""
    tags = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        code = slugify(name, allow_unicode=True) or normalization_key(name)
        tag = ProductTag.objects.filter(store=store, code=code).first()
        if tag is None:
            tag = ProductTag.objects.create(store=store, code=code, name=name)
        elif not tag.is_active:
            tag.is_active = True
            tag.save(update_fields=["is_active", "updated_at"])
        tags.append(tag)
    return tags


def suggest_tags(store, query: str = "", *, limit: int = 20):
    """پیشنهادِ برچسب‌هایِ موجود برایِ تکمیلِ خودکار در فرمِ کالا."""
    qs = ProductTag.objects.filter(store=store, is_active=True)
    if query:
        qs = qs.filter(name__icontains=query)
    return qs.order_by("name")[:limit]


def archive_tag(tag: ProductTag) -> ProductTag:
    if tag.is_active:
        tag.is_active = False
        tag.save(update_fields=["is_active", "updated_at"])
    return tag
