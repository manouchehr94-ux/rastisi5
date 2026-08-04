"""چرخه حیات چیدمان صفحه فروشگاه — Draft / Preview / Publish / Discard / Restore.

قوانین معماری (طبق تصمیمات حل‌شده کاربر، بخش ۳۲ گزارش ممیزی):

- هر عملیات با ``store`` (نه ``layout_id``/``version_id`` خام از ورودی
  کاربر) شروع می‌شود؛ تمام lookupهای بعدی transitively به همان Store
  محدود می‌شوند — این همان تفکیک مستأجر دوگانه (view + سرویس) است که در
  کل کدبیس رعایت شده.
- انتشار (``publish``) کاملاً اتمیک است: تنها کاری که انجام می‌شود عوض
  کردن دو اشاره‌گر (``published_version``/``draft_version``) روی
  ``StorefrontLayout`` است — محتوای نسخه از قبل کامل/معتبر است، پس
  انتشار ناموفق هرگز نمی‌تواند نیمه‌کاره storefront زنده را جایگزین کند.
- بازگردانی (``restore_version``) هرگز مستقیماً منتشر نمی‌شود — همیشه
  یک Draft جدید می‌سازد که باید جداگانه publish شود.
- Rate limiting فقط روی عملیات حساس (publish/restore/ساخت نسخه جدید)
  اعمال می‌شود، نه روی بازچینش معمولی — با استفاده مجدد از
  ``apps.core.services.rate_limit`` موجود، نه یک مکانیزم جدید.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.services.rate_limit import enforce_rate_limit

from ..models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection

_PUBLISH_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
_RESTORE_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
_NEW_DRAFT_RATE_LIMIT = dict(max_attempts=30, window_seconds=3600)


class NoDraftToPublishError(Exception):
    """چیزی برای انتشار وجود ندارد — هیچ Draft فعالی برای این فروشگاه نیست."""


class CrossStoreVersionError(Exception):
    """نسخه‌ی درخواست‌شده متعلق به این فروشگاه نیست."""


def get_or_create_layout(store) -> StorefrontLayout:
    return StorefrontLayout.provision_for(store)


def _next_version_number(layout: StorefrontLayout) -> int:
    last = layout.versions.order_by("-version_number").first()
    return (last.version_number + 1) if last else 1


def _clone_version_content(source: StorefrontLayoutVersion | None, target: StorefrontLayoutVersion) -> None:
    """کپی هدر/فوتر/بخش‌های ``source`` روی ``target`` (که تازه ساخته شده و بدون بخش است)."""
    if source is None:
        return
    target.header_config = dict(source.header_config or {})
    target.footer_config = dict(source.footer_config or {})
    target.save(update_fields=["header_config", "footer_config"])
    sections = [
        StorefrontSection(
            version=target, section_key=s.section_key, order=s.order,
            is_active=s.is_active, settings=dict(s.settings or {}),
        )
        for s in source.sections.order_by("order", "id")
    ]
    if sections:
        StorefrontSection.objects.bulk_create(sections)


@transaction.atomic
def get_or_create_draft(store, *, user=None) -> StorefrontLayoutVersion:
    """Draft فعلی فروشگاه را برمی‌گرداند؛ اگر وجود نداشته باشد، یکی می‌سازد.

    اگر این فروشگاه هرگز هیچ نسخه‌ای نداشته (نه Draft، نه منتشرشده، نه
    بایگانی‌شده) — یعنی اولین بار است که ویرایشگر باز می‌شود — Draft از
    محتوای صفحه اصلی قدیمی (hard-coded) همین فروشگاه بوت‌استرپ می‌شود
    (``bootstrap_service``) تا هرگز بومِ خالی نشان داده نشود. در غیر این
    صورت از روی نسخه‌ی منتشرشده‌ی فعلی کپی می‌شود — تا ویرایشگر همیشه از
    وضعیت فعلیِ زنده شروع شود.
    """
    layout = get_or_create_layout(store)
    if layout.draft_version_id:
        return layout.draft_version

    enforce_rate_limit("storefront_layout.new_draft", str(store.pk), **_NEW_DRAFT_RATE_LIMIT)

    is_first_ever_version = not layout.versions.exists()
    draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=(
            StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP
            if is_first_ever_version else StorefrontLayoutVersion.Source.MANUAL
        ),
        created_by=user if (user and user.is_authenticated) else None,
    )
    if is_first_ever_version:
        from . import bootstrap_service
        bootstrap_service.apply_bootstrap_content(draft, store)
    else:
        _clone_version_content(layout.published_version, draft)
    layout.draft_version = draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return draft


@transaction.atomic
def discard_draft(store) -> None:
    """Draft فعلی را (اگر وجود دارد) حذف می‌کند — بدون اثر روی نسخه منتشرشده."""
    layout = get_or_create_layout(store)
    if not layout.draft_version_id:
        return
    draft = layout.draft_version
    layout.draft_version = None
    layout.save(update_fields=["draft_version", "updated_at"])
    draft.delete()


@transaction.atomic
def publish(store, *, user=None) -> StorefrontLayoutVersion:
    """Draft فعلی را منتشر می‌کند — عملیات اتمیک، فقط تعویض اشاره‌گر.

    نسخه‌ی منتشرشده‌ی قبلی (اگر وجود داشت) به ARCHIVED منتقل می‌شود؛
    Storefront عمومی از این لحظه به بعد نسخه جدید را می‌بیند.
    """
    enforce_rate_limit("storefront_layout.publish", str(store.pk), **_PUBLISH_RATE_LIMIT)

    layout = get_or_create_layout(store)
    draft = layout.draft_version
    if draft is None:
        raise NoDraftToPublishError("هیچ پیش‌نویسی برای انتشار وجود ندارد")

    draft.content_fingerprint = draft.compute_fingerprint()
    draft.status = StorefrontLayoutVersion.Status.PUBLISHED
    draft.published_at = timezone.now()
    draft.save(update_fields=["content_fingerprint", "status", "published_at", "updated_at"])

    previous_published = layout.published_version
    if previous_published is not None:
        previous_published.status = StorefrontLayoutVersion.Status.ARCHIVED
        previous_published.save(update_fields=["status", "updated_at"])

    layout.published_version = draft
    layout.draft_version = None
    layout.uses_visual_storefront_layout = True
    layout.save(update_fields=["published_version", "draft_version", "uses_visual_storefront_layout", "updated_at"])
    return draft


def list_versions(store):
    """تاریخچه‌ی کامل نسخه‌ها (منتشرشده + بایگانی‌شده + پیش‌نویس فعلی، اگر باشد)."""
    layout = get_or_create_layout(store)
    return layout.versions.order_by("-version_number")


@transaction.atomic
def restore_version(store, version_id, *, user=None) -> StorefrontLayoutVersion:
    """محتوای یک نسخه‌ی قدیمی را در یک Draft **جدید** بازمی‌گرداند — هرگز
    مستقیماً منتشر نمی‌شود. اگر Draft فعلی از قبل وجود دارد، جایگزین می‌شود
    (تأیید/هشدار «تغییرات ذخیره‌نشده» مسئولیت لایه UI است، نه این سرویس)."""
    enforce_rate_limit("storefront_layout.restore", str(store.pk), **_RESTORE_RATE_LIMIT)

    layout = get_or_create_layout(store)
    try:
        source = layout.versions.get(pk=version_id)
    except StorefrontLayoutVersion.DoesNotExist:
        raise CrossStoreVersionError(f"نسخه {version_id} متعلق به این فروشگاه نیست") from None

    if layout.draft_version_id:
        old_draft = layout.draft_version
        layout.draft_version = None
        layout.save(update_fields=["draft_version", "updated_at"])
        old_draft.delete()

    new_draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=StorefrontLayoutVersion.Source.RESTORED,
        label=f"بازگردانی از نسخه {source.version_number}",
        created_by=user if (user and user.is_authenticated) else None,
    )
    _clone_version_content(source, new_draft)
    layout.draft_version = new_draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return new_draft
