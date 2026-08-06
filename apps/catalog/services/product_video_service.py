"""لایه‌ی سرویس ویدیوی کالا — فقط لینکِ یوتیوب/آپارات/اینستاگرام، بدونِ
آپلودِ فایل.

تشخیصِ خودکارِ سرویس (یوتیوب/آپارات/اینستاگرام) از رویِ خودِ URL و محاسبه‌ی
``embed_url`` (برایِ ``<iframe>``) این‌جا متمرکز شده تا در view/template
تکرار نشود.

اینستاگرام: چون Instagram معمولاً embedding قابلِ‌اتکا را بدونِ ویجتِ
جاوااسکریپتِ رسمی‌اش (که کاملاً خارج از کنترلِ ماست) یا برایِ کاربرِ
واردنشده تضمین نمی‌کند، به‌جایِ ``<iframe>`` فقط لینکِ عمومیِ معتبر را
ذخیره/اعتبارسنجی می‌کنیم و یک پیش‌نمایشِ امنِ لینکی (بازشونده در تبِ جدید)
نشان می‌دهیم — نه ادعایِ embedِ کامل."""

import re

from django.core.exceptions import ValidationError

from apps.catalog.models import Product, ProductVideo

_YOUTUBE_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtube\.com/shorts/)([\w-]{11})"),
    re.compile(r"youtu\.be/([\w-]{11})"),
    re.compile(r"youtube\.com/embed/([\w-]{11})"),
]
_APARAT_PATTERN = re.compile(r"aparat\.com/(?:v/|video/video/embed/videohash/)([\w-]+)")
# فقط پست/Reel/IGTVِ عمومی — نه پروفایل/صفحه‌ی اصلی.
_INSTAGRAM_PATTERN = re.compile(r"instagram\.com/(p|reel|tv)/([\w-]+)")


class ProductVideoError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ ویدیویِ کالا — مثلاً لینکِ ناشناخته."""


def detect_provider_and_id(url: str):
    """(provider, external_id) را از رویِ URL تشخیص می‌دهد؛ اگر هیچ‌کدام از
    سه سرویسِ پشتیبانی‌شده نبود، ``ProductVideoError`` می‌دهد.

    پیش از تطبیقِ الگو، طرحِ URL باید صریحاً ``http(s)://`` باشد — وگرنه
    یک رشته‌ی دستکاری‌شده مثلِ ``javascript:...//youtube.com/watch?v=...``
    می‌توانست با جست‌وجویِ زیررشته‌ایِ الگوها قبول شود (حتی اگر هرگز به‌صورتِ
    ناامن رندر نشود، ذخیره‌کردنِ چنین مقداری هرگز درست نیست)."""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise ProductVideoError(
            "این لینک شناخته‌شده نیست — فقط لینکِ یوتیوب، آپارات یا پست/Reel عمومیِ اینستاگرام پذیرفته می‌شود."
        )
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return ProductVideo.Provider.YOUTUBE, match.group(1)
    match = _APARAT_PATTERN.search(url)
    if match:
        return ProductVideo.Provider.APARAT, match.group(1)
    match = _INSTAGRAM_PATTERN.search(url)
    if match:
        return ProductVideo.Provider.INSTAGRAM, f"{match.group(1)}/{match.group(2)}"
    raise ProductVideoError(
        "این لینک شناخته‌شده نیست — فقط لینکِ یوتیوب، آپارات یا پست/Reel عمومیِ اینستاگرام پذیرفته می‌شود."
    )


def embed_url(video: ProductVideo) -> str:
    """URLِ قابلِ iframe برایِ یوتیوب/آپارات. برایِ اینستاگرام None برمی‌گرداند
    (نگاه کنید به ``instagram_permalink`` — به‌جایش لینکِ امنِ بازشونده در
    تبِ جدید نمایش داده می‌شود، نه iframe)."""
    if video.provider == ProductVideo.Provider.INSTAGRAM:
        return None
    _, external_id = detect_provider_and_id(video.url)
    if video.provider == ProductVideo.Provider.YOUTUBE:
        return f"https://www.youtube.com/embed/{external_id}"
    return f"https://www.aparat.com/video/video/embed/videohash/{external_id}/vt/frame"


def instagram_permalink(video: ProductVideo) -> str:
    """لینکِ عمومیِ اصلاح‌شده‌ی اینستاگرام برایِ نمایشِ «بازکردن در اینستاگرام»."""
    _, external_id = detect_provider_and_id(video.url)
    kind, shortcode = external_id.split("/")
    return f"https://www.instagram.com/{kind}/{shortcode}/"


def add_product_video(product: Product, *, url: str, title: str = "") -> ProductVideo:
    provider, _external_id = detect_provider_and_id(url)
    video = ProductVideo(
        product=product, provider=provider, url=url, title=title,
        display_order=product.videos.count(),
    )
    try:
        video.full_clean()
    except ValidationError as exc:
        raise ProductVideoError("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    video.save()
    return video


def delete_product_video(video: ProductVideo) -> None:
    video.delete()
