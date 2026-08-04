"""ویوهای داشبورد سازنده بصری صفحه فروشگاه — همگی پشت
``STOREFRONT_LAYOUT_MANAGE`` (نه ``CONTENT_MANAGE``، طبق تصمیم کاربر)."""

from django.contrib import messages
from django.db import IntegrityError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import section_registry
from .models import StorefrontLayoutVersion, StorefrontSection
from .services import layout_service
from .services.render_service import build_render_items


def _resolve_store(request):
    return resolve_store_for_service(request)


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    layout = layout_service.get_or_create_layout(store)
    sections = draft.sections.order_by("order", "id")
    context = {
        "active_page": "storefront_builder",
        "layout": layout,
        "draft": draft,
        "sections": sections,
        "section_definitions": section_registry.list_definitions(),
        "versions": layout_service.list_versions(store),
    }
    return render(request, "dashboard/storefront_builder/editor.html", context)


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_preview(request):
    """پیش‌نمایش تمام‌صفحه‌ی Draft فعلی — فقط برای staff همین فروشگاه؛ هرگز
    برای بازدیدکننده عمومی در دسترس نیست (تصمیم ۱۱ کاربر)."""
    from apps.catalog.models import Category

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    items = build_render_items(draft, store)
    top_level_categories = Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
    return render(request, "storefront_builder/preview.html", {
        "store": store, "version": draft, "render_items": items, "is_preview": True,
        "top_level_categories": top_level_categories,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_list_partial(request):
    """پارشیال لیست بخش‌ها — برای بازآوری htmx پس از هر تغییر."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    context = {
        "draft": draft,
        "sections": draft.sections.order_by("order", "id"),
        "section_definitions": section_registry.list_definitions(),
    }
    return render(request, "dashboard/storefront_builder/partials/section_list.html", context)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_add(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    section_key = request.POST.get("section_key", "")

    try:
        definition = section_registry.get_definition(section_key)
    except section_registry.UnknownSectionTypeError:
        return HttpResponseBadRequest("نوع بخش نامعتبر است")

    existing_count = draft.sections.filter(section_key=section_key).count()
    if definition.max_instances is not None and existing_count >= definition.max_instances:
        messages.error(request, f"«{definition.label_fa}» فقط یک بار قابل افزودن است")
        return storefront_section_list_partial(request)

    last = draft.sections.order_by("-order").first()
    new_order = (last.order + 1) if last else 0
    StorefrontSection.objects.create(
        version=draft, section_key=section_key, order=new_order,
        settings=definition.default_settings(),
    )
    messages.success(request, f"«{definition.label_fa}» اضافه شد")
    return storefront_section_list_partial(request)


def _get_scoped_section(request, pk):
    store = _resolve_store(request)
    return get_object_or_404(
        StorefrontSection, pk=pk, version__layout__store=store,
        version__status=StorefrontLayoutVersion.Status.DRAFT,
    )


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_settings(request, pk):
    """فرم ویرایش تنظیمات — فقط برای انواعی که واقعاً محتوای قابل‌تنظیم
    دارند (``has_settings_form``)؛ هیچ فیلد JSON/HTML خام به تاجر نشان
    داده نمی‌شود، فقط فیلدهای فرم واقعی (عنوان، متن غنی از طریق CKEditor
    موجود، آدرس تصویر)."""
    section = _get_scoped_section(request, pk)
    try:
        definition = section_registry.get_definition(section.section_key)
    except section_registry.UnknownSectionTypeError:
        raise Http404
    if not definition.has_settings_form:
        raise Http404

    field_errors = {}
    if request.method == "POST":
        raw = {
            "title": request.POST.get("title", ""),
            "body_html": request.POST.get("body_html", ""),
            "image_url": request.POST.get("image_url", ""),
            "image_position": request.POST.get("image_position", "right"),
        }
        try:
            cleaned = definition.validate_settings(raw)
            section.settings = cleaned
            section.save(update_fields=["settings", "updated_at"])
            messages.success(request, "تنظیمات ذخیره شد")
            return redirect("dashboard:storefront-builder-editor")
        except ValueError as exc:
            field_errors["general"] = str(exc)

    return render(request, "dashboard/storefront_builder/partials/section_settings_form.html", {
        "section": section, "definition": definition, "field_errors": field_errors,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_remove(request, pk):
    section = _get_scoped_section(request, pk)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.removable:
            messages.error(request, f"«{definition.label_fa}» قابل حذف نیست")
            return storefront_section_list_partial(request)
    except section_registry.UnknownSectionTypeError:
        pass
    section.delete()
    messages.success(request, "بخش حذف شد")
    return storefront_section_list_partial(request)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_toggle(request, pk):
    section = _get_scoped_section(request, pk)
    section.is_active = not section.is_active
    section.save(update_fields=["is_active", "updated_at"])
    return storefront_section_list_partial(request)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_duplicate(request, pk):
    section = _get_scoped_section(request, pk)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.duplicable:
            messages.error(request, f"«{definition.label_fa}» قابل تکرار نیست")
            return storefront_section_list_partial(request)
    except section_registry.UnknownSectionTypeError:
        pass
    last = section.version.sections.order_by("-order").first()
    new_order = (last.order + 1) if last else 0
    StorefrontSection.objects.create(
        version=section.version, section_key=section.section_key,
        order=new_order, is_active=section.is_active, settings=dict(section.settings or {}),
    )
    messages.success(request, "بخش تکرار شد")
    return storefront_section_list_partial(request)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_reorder(request):
    """قرارداد یکسان با سایر endpointهای reorder موجود (product-image،
    brand، دسته‌بندی و ...): ``section_ids`` فرم‌رمزی‌شده، سرویس دوباره بر
    اساس تفکیک مستأجر فیلتر می‌کند، شناسه نامعتبر/خارجی بی‌صدا حذف می‌شود،
    ``enumerate()`` ترتیب را از نو ۰..N تنظیم می‌کند."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    section_ids = request.POST.getlist("section_ids")

    valid_ids = set(draft.sections.values_list("pk", flat=True))
    ordered_ids = [int(i) for i in section_ids if i.isdigit() and int(i) in valid_ids]

    from django.db import transaction
    with transaction.atomic():
        for index, section_id in enumerate(ordered_ids):
            StorefrontSection.objects.filter(pk=section_id, version=draft).update(order=index)

    return storefront_section_list_partial(request)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_move(request, pk):
    """جابه‌جایی یک بخش به بالا/پایین — fallback برای موبایل/کیبورد وقتی
    drag-and-drop عملی نیست."""
    direction = request.POST.get("direction")
    section = _get_scoped_section(request, pk)
    siblings = list(section.version.sections.order_by("order", "id"))
    index = next((i for i, s in enumerate(siblings) if s.pk == section.pk), None)
    if index is None:
        return storefront_section_list_partial(request)

    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(siblings):
        other = siblings[swap_index]
        section.order, other.order = other.order, section.order
        StorefrontSection.objects.bulk_update([section, other], ["order"])
    return storefront_section_list_partial(request)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_publish(request):
    store = _resolve_store(request)
    try:
        layout_service.publish(store, user=request.user)
        messages.success(request, "چیدمان جدید منتشر شد")
    except layout_service.NoDraftToPublishError:
        messages.error(request, "پیش‌نویسی برای انتشار وجود ندارد")
    except Exception:
        messages.error(request, "محدودیت تعداد انتشار — کمی بعد دوباره تلاش کنید")
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_discard(request):
    store = _resolve_store(request)
    layout_service.discard_draft(store)
    messages.success(request, "پیش‌نویس رد شد")
    return redirect("dashboard:storefront-builder-editor")


_HEADER_TOGGLE_FIELDS = ["show_search", "show_account", "show_cart", "show_wishlist", "sticky", "announcement_enabled"]
_HEADER_DEFAULTS = {f: True for f in _HEADER_TOGGLE_FIELDS} | {"announcement_text": ""}

_FOOTER_TOGGLE_FIELDS = [
    "show_about", "show_contact", "show_quick_links", "show_categories",
    "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter", "show_copyright",
]
_FOOTER_DEFAULTS = {f: True for f in _FOOTER_TOGGLE_FIELDS}


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_header_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        config = dict(_HEADER_DEFAULTS)
        for field in _HEADER_TOGGLE_FIELDS:
            config[field] = request.POST.get(field) == "on"
        config["announcement_text"] = request.POST.get("announcement_text", "")[:300]
        draft.header_config = config
        draft.save(update_fields=["header_config", "updated_at"])
        messages.success(request, "تنظیمات هدر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    config = {**_HEADER_DEFAULTS, **(draft.header_config or {})}
    return render(request, "dashboard/storefront_builder/header_editor.html", {
        "active_page": "storefront_builder", "config": config, "draft": draft,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_footer_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        config = dict(_FOOTER_DEFAULTS)
        for field in _FOOTER_TOGGLE_FIELDS:
            config[field] = request.POST.get(field) == "on"
        draft.footer_config = config
        draft.save(update_fields=["footer_config", "updated_at"])
        messages.success(request, "تنظیمات فوتر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    config = {**_FOOTER_DEFAULTS, **(draft.footer_config or {})}
    return render(request, "dashboard/storefront_builder/footer_editor.html", {
        "active_page": "storefront_builder", "config": config, "draft": draft,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_history(request):
    store = _resolve_store(request)
    versions = layout_service.list_versions(store)
    layout = layout_service.get_or_create_layout(store)
    return render(request, "dashboard/storefront_builder/history.html", {
        "active_page": "storefront_builder", "versions": versions, "layout": layout,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_restore(request, pk):
    store = _resolve_store(request)
    try:
        layout_service.restore_version(store, pk, user=request.user)
        messages.success(request, "نسخه در یک پیش‌نویس جدید بازگردانی شد — برای اعمال آن روی فروشگاه، آن را منتشر کنید")
    except layout_service.CrossStoreVersionError:
        raise Http404
    except Exception:
        messages.error(request, "محدودیت تعداد بازگردانی — کمی بعد دوباره تلاش کنید")
    return redirect("dashboard:storefront-builder-editor")
