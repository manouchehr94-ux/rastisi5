"""ویوهای داشبورد سازنده بصری صفحه فروشگاه — همگی پشت
``STOREFRONT_LAYOUT_MANAGE`` (نه ``CONTENT_MANAGE``، طبق تصمیم کاربر)."""

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import section_registry
from .models import (
    FOOTER_CONFIG_DEFAULTS,
    FOOTER_TOGGLE_FIELDS,
    HEADER_CONFIG_DEFAULTS,
    HEADER_TOGGLE_FIELDS,
    StorefrontLayoutVersion,
    StorefrontSection,
)
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
    industry_installation = getattr(store, "industry_installation", None)
    context = {
        "active_page": "storefront_builder",
        "layout": layout,
        "draft": draft,
        "sections": sections,
        "section_definitions": section_registry.list_definitions(),
        "versions": layout_service.list_versions(store),
        "industry_installation": industry_installation,
    }
    return render(request, "dashboard/storefront_builder/editor.html", context)


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@xframe_options_sameorigin
def storefront_preview(request):
    """پیش‌نمایش تمام‌صفحه‌ی Draft فعلی — فقط برای staff همین فروشگاه؛ هرگز
    برای بازدیدکننده عمومی در دسترس نیست (تصمیم ۱۱ کاربر).

    ``xframe_options_sameorigin`` صراحتاً override می‌کند چون این ویو عمداً
    داخل iframe ادیتور embed می‌شود؛ پیش‌فرض سراسری DENY (میدل‌ور
    XFrameOptionsMiddleware بدون X_FRAME_OPTIONS) برای همه‌ی ویوهای دیگر
    دست‌نخورده باقی می‌ماند."""
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
        if section.section_key == "product_section":
            raw = {
                "data_source": request.POST.get("data_source", ""),
                "source_id": request.POST.get("source_id") or None,
                "product_ids": request.POST.getlist("product_ids"),
                "item_limit": request.POST.get("item_limit", ""),
                "display_mode": request.POST.get("display_mode", ""),
                "show_view_all": request.POST.get("show_view_all") == "on",
                "title": request.POST.get("title", ""),
                "subtitle": request.POST.get("subtitle", ""),
            }
        elif section.section_key == "image_text":
            raw = {
                "title": request.POST.get("title", ""),
                "body_html": request.POST.get("body_html", ""),
                "image_url": request.POST.get("image_url", ""),
                "image_position": request.POST.get("image_position", "right"),
            }
        elif section.section_key == "rich_text":
            raw = {"body_html": request.POST.get("body_html", "")}
        else:
            # انواعی که هیچ فیلدِ اختصاصیِ خودشان را ندارند (فازِ D) —
            # تنها چیزی که این فرم برایشان دارد بلوکِ responsive است.
            raw = {}
        raw["responsive"] = _extract_responsive_raw(request, section.section_key)
        try:
            cleaned = definition.validate_settings(raw)
            section.settings = cleaned
            section.save(update_fields=["settings", "updated_at"])
            messages.success(request, "تنظیمات ذخیره شد")
            return redirect("dashboard:storefront-builder-editor")
        except ValueError as exc:
            field_errors["general"] = str(exc)

    context = {
        "section": section, "definition": definition, "field_errors": field_errors,
        "supports_columns": section.section_key in section_registry.COLUMN_AWARE_SECTION_KEYS,
    }
    if section.section_key == "product_section":
        context.update(_product_section_picker_context(request, section))
    return render(request, "dashboard/storefront_builder/partials/section_settings_form.html", context)


def _extract_responsive_raw(request, section_key: str) -> dict:
    """بلوکِ خامِ «تنظیماتِ نمایش در دستگاه‌ها» را از POST می‌خواند —
    یک بار نوشته شده، توسطِ فرمِ تنظیماتِ هر ۱۷ نوعِ section استفاده
    می‌شود (بخشِ ۶ مشخصات: «Use one shared helper where possible»).
    مرچنت در قالبِ مثبت («نمایش در…») تیک می‌زند؛ اینجا به مدلِ
    hide_on_* (منفی، قراردادِ ذخیره‌سازی) تبدیل می‌شود."""
    raw = {
        "hide_on_desktop": request.POST.get("show_on_desktop") != "on",
        "hide_on_tablet": request.POST.get("show_on_tablet") != "on",
        "hide_on_mobile": request.POST.get("show_on_mobile") != "on",
    }
    if section_key in section_registry.COLUMN_AWARE_SECTION_KEYS:
        raw["desktop_columns"] = request.POST.get("desktop_columns")
        raw["tablet_columns"] = request.POST.get("tablet_columns")
        raw["mobile_columns"] = request.POST.get("mobile_columns")
    return raw


def _product_section_picker_context(request, section):
    """کالکشن‌ها/دسته‌بندی‌ها/برندهایِ همین Store (برایِ کشوهای انتخابِ
    منبع) + کالاهایِ دستیِ فعلاً انتخاب‌شده (برایِ نمایشِ اولیه‌یِ
    چیپ‌هایِ ادیتور «کالاهایِ دستی» — نه بازسازیِ آن‌ها از صفر در JS)."""
    from apps.catalog.models import Brand, Category, MerchantCollection, Product

    store = _resolve_store(request)
    product_ids = section.settings.get("product_ids") or []
    products_by_id = {p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids)}
    return {
        "collections": MerchantCollection.objects.filter(store=store).order_by("name"),
        "categories": Category.objects.filter(store=store).order_by("name"),
        "brands": Brand.objects.filter(store=store).order_by("name"),
        "initial_manual_products": [
            {"id": pid, "name": products_by_id[pid].name} for pid in product_ids if pid in products_by_id
        ],
    }


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_product_search(request, pk):
    """جست‌وجویِ کالا برایِ ویجتِ «کالاهایِ دستی» تنظیماتِ بخشِ محصول —
    از همان ``collection_service.searchable_products`` فازِ B عبور
    می‌کند (نه پیاده‌سازیِ دوباره‌ی جست‌وجو)."""
    from apps.catalog.services import collection_service

    _get_scoped_section(request, pk)
    store = _resolve_store(request)
    query = request.GET.get("q", "").strip()
    results = collection_service.searchable_products(store, query=query)[:20] if query else []
    return render(request, "dashboard/storefront_builder/partials/product_section_search_results.html", {
        "results": results, "query": query,
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
def storefront_section_collapse_toggle(request, pk):
    """جمع‌کردن/بازکردن کارت یک بخش داخل ادیتور — فقط UI، مستقل از
    is_active (A3). ``_get_scoped_section`` تضمین می‌کند فقط بخش‌های
    همین فروشگاه و فقط در نسخه Draft قابل تغییرند."""
    section = _get_scoped_section(request, pk)
    section.collapsed_in_editor = not section.collapsed_in_editor
    section.save(update_fields=["collapsed_in_editor", "updated_at"])
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
    ``enumerate()`` ترتیب را از نو ۰..N تنظیم می‌کند.

    A4: شناسه‌ی تکراری کل عملیات را رد می‌کند (هیچ ردیفی تغییر نمی‌کند)؛
    کل حلقه‌ی به‌روزرسانی داخل یک تراکنش است — یا ترتیبِ کامل ذخیره
    می‌شود یا هیچ‌کدام."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    section_ids = request.POST.getlist("section_ids")

    valid_ids = set(draft.sections.values_list("pk", flat=True))
    ordered_ids = [int(i) for i in section_ids if i.isdigit() and int(i) in valid_ids]

    if len(set(ordered_ids)) != len(ordered_ids):
        messages.error(request, "فهرست مرتب‌سازی شامل شناسه‌ی تکراری است — ترتیب تغییر نکرد")
        return storefront_section_list_partial(request)

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
def storefront_apply_industry_layout(request):
    """چیدمان پیشنهادیِ صنفِ نصب‌شده‌ی این فروشگاه را در یک Draft جدید اعمال
    می‌کند. اگر فروشگاه از قبل یک نسخه‌ی منتشرشده دارد، بدون
    ``confirm=1`` (تأیید صریح کاربر در UI) رد می‌شود — هرگز بی‌صدا
    storefront منتشرشده را رونویسی نمی‌کند."""
    store = _resolve_store(request)
    installation = getattr(store, "industry_installation", None)
    if installation is None:
        raise Http404
    force = request.POST.get("confirm") == "1"
    try:
        layout_service.apply_industry_layout(
            store, installation.industry_template, user=request.user, force=force,
        )
        messages.success(request, "چیدمان پیشنهادی صنف در یک پیش‌نویس جدید اعمال شد")
    except layout_service.StorefrontAlreadyPublishedError:
        messages.error(
            request,
            "این فروشگاه از قبل یک نسخه‌ی منتشرشده دارد — برای رونویسی آن با چیدمان صنف، "
            "دوباره با تأیید صریح تلاش کنید",
        )
    except Exception:
        messages.error(request, "محدودیت تعداد ساخت نسخه — کمی بعد دوباره تلاش کنید")
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_discard(request):
    store = _resolve_store(request)
    layout_service.discard_draft(store)
    messages.success(request, "پیش‌نویس رد شد")
    return redirect("dashboard:storefront-builder-editor")


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_header_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        raw = {field: request.POST.get(field) == "on" for field in HEADER_TOGGLE_FIELDS}
        raw["announcement_text"] = request.POST.get("announcement_text", "")
        try:
            config = layout_service.validate_header_config(raw)
        except layout_service.HeaderConfigValidationError as exc:
            messages.error(request, str(exc))
            return render(request, "dashboard/storefront_builder/header_editor.html", {
                "active_page": "storefront_builder",
                "config": {**HEADER_CONFIG_DEFAULTS, **raw}, "draft": draft, "error": str(exc),
            })
        draft.header_config = config
        draft.save(update_fields=["header_config", "updated_at"])
        messages.success(request, "تنظیمات هدر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    return render(request, "dashboard/storefront_builder/header_editor.html", {
        "active_page": "storefront_builder", "config": draft.effective_header_config(), "draft": draft,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_footer_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        raw = {field: request.POST.get(field) == "on" for field in FOOTER_TOGGLE_FIELDS}
        try:
            config = layout_service.validate_footer_config(raw)
        except layout_service.FooterConfigValidationError as exc:
            messages.error(request, str(exc))
            return render(request, "dashboard/storefront_builder/footer_editor.html", {
                "active_page": "storefront_builder",
                "config": {**FOOTER_CONFIG_DEFAULTS, **raw}, "draft": draft, "error": str(exc),
            })
        draft.footer_config = config
        draft.save(update_fields=["footer_config", "updated_at"])
        messages.success(request, "تنظیمات فوتر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    return render(request, "dashboard/storefront_builder/footer_editor.html", {
        "active_page": "storefront_builder", "config": draft.effective_footer_config(), "draft": draft,
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
