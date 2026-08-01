"""لایه‌ی سرویس ویدیوی کالا — فقط لینکِ یوتیوب/آپارات، بدونِ آپلودِ فایل.

تشخیصِ خودکارِ سرویس (یوتیوب/آپارات) از رویِ خودِ URL و محاسبه‌ی
``embed_url`` (برایِ ``<iframe>``) این‌جا متمرکز شده تا در view/template
تکرار نشود.
"""

import re

from django.core.exceptions import ValidationError

from apps.catalog.models import Product, ProductVideo

_YOUTUBE_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtube\.com/shorts/)([\w-]{11})"),
    re.compile(r"youtu\.be/([\w-]{11})"),
    re.compile(r"youtube\.com/embed/([\w-]{11})"),
]
_APARAT_PATTERN = re.compile(r"aparat\.com/(?:v/|video/video/embed/videohash/)([\w-]+)")


class ProductVideoError(Exception):
    """خطای قابل‌نمایش هنگام مدیریتِ ویدیویِ کالا — مثلاً لینکِ ناشناخته."""


def detect_provider_and_id(url: str):
    """(provider, external_id) را از رویِ URL تشخیص می‌دهد؛ اگر نه یوتیوب بود
    نه آپارات، ``ProductVideoError`` می‌دهد — فقط این دو سرویس پشتیبانی می‌شوند."""
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return ProductVideo.Provider.YOUTUBE, match.group(1)
    match = _APARAT_PATTERN.search(url)
    if match:
        return ProductVideo.Provider.APARAT, match.group(1)
    raise ProductVideoError("این لینک شناخته‌شده نیست — فقط لینکِ یوتیوب یا آپارات پذیرفته می‌شود.")


def embed_url(video: ProductVideo) -> str:
    _, external_id = detect_provider_and_id(video.url)
    if video.provider == ProductVideo.Provider.YOUTUBE:
        return f"https://www.youtube.com/embed/{external_id}"
    return f"https://www.aparat.com/video/video/embed/videohash/{external_id}/vt/frame"


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
