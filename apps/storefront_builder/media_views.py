"""ویوهای مدیریتِ رسانه‌یِ مخصوصِ یک section — اسلایدهایِ اسلایدرِ اصلی
(``HeroSlide``) و بنرها (``PromotionalBanner``)، هر دو از داخلِ سازنده
بصری، مقیّد به یک نمونه‌یِ مشخص از section (نه فهرستِ سراسریِ فروشگاه).

این ماژول عمداً از ``views.py`` جدا نگه داشته شده — منطقِ CRUD رسانه با
منطقِ CRUD خودِ section کاملاً متفاوت است (آپلودِ فایل، دو مدلِ مختلف)،
اما هر دو مدل (``HeroSlide``/``PromotionalBanner``) از نظرِ شکلِ فرم آنقدر
شبیه‌هم‌اند که یک پیاده‌سازیِ عمومیِ واحد (پارامتری‌شده با ``kind``) به‌جایِ
دو کپیِ تقریباً یکسان انتخاب شده — دقیقاً همان اصلِ «بدون معماریِ یک‌بارمصرفِ
جداگانه برایِ هر section جدید» که مستندسازیِ ``section_registry.py`` تأکید
می‌کند.

قوانینِ حیاتی که این ماژول باید حفظ کند:
- هر عملیات با ``_get_scoped_section`` شروع می‌شود (همان تابعِ ``views.py``) —
  یعنی مقیّد به Store + نسخه‌یِ Draft، دقیقاً همان محافظتِ دوگانه‌یِ مستأجر
  که بقیه‌یِ endpointهایِ section دارند.
- آپلود/حذفِ فایل دقیقاً همان الگویِ امنِ ``apps.dashboard.views.hero_form``
  (پاک‌سازیِ فایلِ قدیمی فقط پس از commit موفق) را تکرار می‌کند — نه
  ساده‌سازیِ آن.
"""

from __future__ import annotations

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem
from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE

from .views import _get_scoped_section, _resolve_store

#: پیکربندیِ عمومیِ هر دو نوعِ رسانه — کلیدِ URL (``kind``) → مدل + برچسبِ
#: فارسی + نامِ فیلدِ متنِ دومِ اختصاصی (``subtitle`` برایِ اسلاید،
#: ``description`` برایِ بنر) + مسیرِ section_key هایی که این رسانه را
#: مصرف می‌کنند (فقط برایِ اعتبارسنجیِ ورودیِ URL، نه چیزِ دیگر).
_MEDIA_KINDS = {
    "hero-slides": {
        "model": HeroSlide,
        "label": "اسلاید",
        "label_plural": "اسلایدها",
        "text_field": "subtitle",
        "text_label": "زیرعنوان",
        "section_keys": {"hero_banner", "image_slider"},
    },
    "banners": {
        "model": PromotionalBanner,
        "label": "بنر",
        "label_plural": "بنرها",
        "text_field": "description",
        "text_label": "توضیحات",
        "section_keys": {"single_banner", "multi_banner"},
    },
    "story-items": {
        "model": StoryRailItem,
        "label": "آیتم استوری",
        "label_plural": "آیتم‌های استوری",
        "text_field": "title",
        "text_label": "عنوان",
        "section_keys": {"story_rail"},
        "image_field": "image",  # single image, not desktop/mobile pair
    },
}


def _media_config(kind: str, section) -> dict:
    config = _MEDIA_KINDS.get(kind)
    if config is None:
        raise Http404
    if section.section_key not in config["section_keys"]:
        raise Http404
    return config


def _media_list_body(request, section, kind, config):
    """پارشیالِ فهرستِ آیتم‌ها — یک بار نوشته شده، هم توسطِ صفحه‌ی کامل و هم
    توسطِ هر endpointِ htmx (toggle/delete/reorder/move) برایِ reswap
    استفاده می‌شود؛ دقیقاً همان الگویِ ``storefront_section_list_partial``
    برایِ خودِ section."""
    items = config["model"].objects.filter(section=section).order_by("display_order", "id")
    return render(request, "dashboard/storefront_builder/partials/section_media_list_body.html", {
        "section": section, "items": items, "kind": kind, "config": config,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_list(request, pk, kind):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    items = config["model"].objects.filter(section=section).order_by("display_order", "id")
    return render(request, "dashboard/storefront_builder/section_media_list.html", {
        "section": section, "items": items, "kind": kind, "config": config,
    })


def _apply_destination_fields(obj, request):
    obj.destination_type = request.POST.get("destination_type", "none")
    obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
    obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"
    cat_id = request.POST.get("destination_category") or None
    prod_id = request.POST.get("destination_product") or None
    brand_id = request.POST.get("destination_brand") or None
    collection_id = request.POST.get("destination_collection") or None
    obj.destination_category_id = int(cat_id) if cat_id else None
    obj.destination_product_id = int(prod_id) if prod_id else None
    obj.destination_brand_id = int(brand_id) if brand_id else None
    obj.destination_collection_id = int(collection_id) if collection_id else None


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_form(request, pk, kind, item_pk=None):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    model = config["model"]
    store = _resolve_store(request)
    item = get_object_or_404(model, pk=item_pk, section=section) if item_pk else None

    if request.method == "POST":
        obj = item or model(store=store, section=section)
        old_desktop_name = obj.desktop_image.name if obj.pk and obj.desktop_image else None
        old_mobile_name = obj.mobile_image.name if obj.pk and obj.mobile_image else None

        obj.title = request.POST.get("title", "").strip()
        setattr(obj, config["text_field"], request.POST.get(config["text_field"], "").strip())
        obj.button_label = request.POST.get("button_label", "").strip()
        obj.show_button = request.POST.get("show_button") == "on"
        obj.is_active = request.POST.get("is_active", "on") == "on"
        if not item:
            last = model.objects.filter(section=section).order_by("-display_order").first()
            obj.display_order = (last.display_order + 1) if last else 0
        _apply_destination_fields(obj, request)

        if "desktop_image" in request.FILES:
            obj.desktop_image = request.FILES["desktop_image"]
        if "mobile_image" in request.FILES:
            obj.mobile_image = request.FILES["mobile_image"]
        if request.POST.get("remove_mobile") == "on" and "mobile_image" not in request.FILES:
            obj.mobile_image = ""

        try:
            obj.full_clean()
            obj.save()
            storage = model.desktop_image.field.storage
            new_desktop_name = obj.desktop_image.name if obj.desktop_image else None
            new_mobile_name = obj.mobile_image.name if obj.mobile_image else None
            files_to_delete = [
                name for name in (
                    old_desktop_name if old_desktop_name != new_desktop_name else None,
                    old_mobile_name if old_mobile_name != new_mobile_name else None,
                ) if name
            ]
            if files_to_delete:
                transaction.on_commit(lambda: [storage.delete(f) for f in files_to_delete if storage.exists(f)])
            messages.success(request, f"«{config['label']}» ذخیره شد")
            return redirect("dashboard:storefront-builder-section-media-list", pk=section.pk, kind=kind)
        except (ValidationError, IntegrityError) as exc:
            error_message = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, error_message)
            item = obj

    from apps.catalog.models import Category

    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")
    return render(request, "dashboard/storefront_builder/partials/section_media_form.html", {
        "section": section, "item": item, "kind": kind, "config": config, "categories": categories,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_delete(request, pk, kind, item_pk):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    item = get_object_or_404(config["model"], pk=item_pk, section=section)
    desktop_name = item.desktop_image.name if item.desktop_image else None
    mobile_name = item.mobile_image.name if item.mobile_image else None
    storage = item.desktop_image.storage

    item.delete()

    def _cleanup():
        if desktop_name and storage.exists(desktop_name):
            storage.delete(desktop_name)
        if mobile_name and storage.exists(mobile_name):
            storage.delete(mobile_name)

    transaction.on_commit(_cleanup)
    messages.success(request, f"«{config['label']}» حذف شد")
    return _media_list_body(request, section, kind, config)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_toggle(request, pk, kind, item_pk):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    item = get_object_or_404(config["model"], pk=item_pk, section=section)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active", "updated_at"])
    return _media_list_body(request, section, kind, config)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_move(request, pk, kind, item_pk):
    """جابه‌جاییِ یک آیتم به بالا/پایین — fallback برایِ موبایل/کیبورد،
    دقیقاً همان الگویِ ``storefront_section_move`` برایِ خودِ section."""
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    model = config["model"]
    direction = request.POST.get("direction")
    item = get_object_or_404(model, pk=item_pk, section=section)
    siblings = list(model.objects.filter(section=section).order_by("display_order", "id"))
    index = next((i for i, s in enumerate(siblings) if s.pk == item.pk), None)
    if index is not None:
        swap_index = index - 1 if direction == "up" else index + 1
        if 0 <= swap_index < len(siblings):
            other = siblings[swap_index]
            item.display_order, other.display_order = other.display_order, item.display_order
            model.objects.bulk_update([item, other], ["display_order"])
    return _media_list_body(request, section, kind, config)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_media_reorder(request, pk, kind):
    section = _get_scoped_section(request, pk)
    config = _media_config(kind, section)
    model = config["model"]
    item_ids = request.POST.getlist("item_ids")

    valid_ids = set(model.objects.filter(section=section).values_list("pk", flat=True))
    ordered_ids = [int(i) for i in item_ids if i.isdigit() and int(i) in valid_ids]

    if len(set(ordered_ids)) != len(ordered_ids):
        messages.error(request, "فهرست مرتب‌سازی شامل شناسه‌ی تکراری است — ترتیب تغییر نکرد")
        return _media_list_body(request, section, kind, config)

    with transaction.atomic():
        for index, item_id in enumerate(ordered_ids):
            model.objects.filter(pk=item_id, section=section).update(display_order=index)

    return _media_list_body(request, section, kind, config)
