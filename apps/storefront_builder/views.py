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
    APPEARANCE_CONFIG_DEFAULTS,
    FOOTER_CONFIG_DEFAULTS,
    FOOTER_RESPONSIVE_AWARE_KEYS,
    FOOTER_TOGGLE_FIELDS,
    HEADER_CONFIG_DEFAULTS,
    HEADER_RESPONSIVE_AWARE_KEYS,
    HEADER_TOGGLE_FIELDS,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from .services import layout_service
from .services.layout_service import _clone_section_scoped_media
from .services.render_service import build_page_render_items


def _resolve_store(request):
    return resolve_store_for_service(request)


def _resolve_page_type(raw) -> str:
    """Phase 2 (سازنده‌ی تک‌صفحه‌ای): رشته‌یِ خامِ ``page`` (از querystring
    یا فرمِ POST) را به یکی از شش نوعِ معتبرِ ``StorefrontPage.PageType``
    حل می‌کند — مقدارِ غایب/نامعتبر بی‌صدا به ``HOME`` بازمی‌گردد (نه
    خطا) تا لینک/فرمِ قدیمیِ بدونِ این پارامتر (پیش از این چکپوینت)
    دقیقاً همان رفتارِ فعلی را حفظ کند."""
    if raw in StorefrontPage.PageType.values:
        return raw
    return StorefrontPage.PageType.HOME


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    layout = layout_service.get_or_create_layout(store)
    # Phase 2 (سازنده‌ی تک‌صفحه‌ای): صفحه‌یِ در حالِ ویرایش از
    # ``?page=<page_type>`` (وضعیتِ صریح در URL) حل می‌شود — غیاب/نامعتبر
    # بودنِ آن دقیقاً معادلِ رفتارِ قبل از این چکپوینت (همیشه صفحه‌ی
    # اصلی) است.
    page_type = _resolve_page_type(request.GET.get("page"))
    page = draft.get_page(page_type)
    sections = page.sections.order_by("order", "id")
    industry_installation = getattr(store, "industry_installation", None)
    context = {
        "active_page": "storefront_builder",
        "layout": layout,
        "draft": draft,
        "page": page,
        "page_type": page_type,
        "page_types": StorefrontPage.PageType.choices,
        "sections": sections,
        "section_definitions": section_registry.list_definitions(),
        "section_library_groups": section_registry.list_library_groups(page_type=page_type),
        "versions": layout_service.list_versions(store),
        "industry_installation": industry_installation,
    }
    return render(request, "dashboard/storefront_builder/editor.html", context)


class _CandidateAppearanceVersion:
    """جای‌گزینِ سبکِ ``StorefrontLayoutVersion`` برایِ پیش‌نمایشِ
    غیرمخربِ یک Templateِ کاندید (چکپوینتِ «پیش‌نمایشِ قبل از اعمال»،
    بخشِ ۱۰ بازبینیِ نهایی) — فقط همان یک متدی را دارد که
    ``apps.core.context_processors`` روی ``request.storefront_appearance_version``
    صدا می‌زند (``effective_appearance_config``)، هرگز به دیتابیس
    نمی‌نویسد. تعویضِ template_slug دقیقاً همان معنایی را دارد که
    ``storefront_appearance_editor`` هنگامِ POSTِ واقعیِ تعویض اعمال
    می‌کند (فیلدهایِ ساختاری به پیش‌فرض‌هایِ همان Template بازنشانی
    می‌شوند) — تا پیش‌نمایش دقیقاً همان چیزی باشد که اعمالِ واقعی تولید
    می‌کند."""

    def __init__(self, base_config, *, template_slug=None):
        from . import appearance_registry

        config = dict(base_config)
        if template_slug is not None:
            config["template_slug"] = template_slug
            template = appearance_registry.get_template(template_slug)
            if template is not None:
                for field in ("font", "radius", "button_radius", "density", "motion", "type_scale"):
                    config[field] = getattr(template, field)
        self._config = config

    def effective_appearance_config(self):
        return self._config


def _preview_page_context(request, store, page_type: str) -> dict:
    """Phase 5: معادلِ ``page_context``یِ مسیرِ عمومی، اما برایِ Preview که
    هیچ «محصول/کالکشن/جستجویِ جاری» واقعی از URL ندارد — یک نمونه‌یِ
    نماینده (جدیدترین محصول/کالکشن همین Store) با **همان توابعِ** مسیرِ
    عمومی ساخته می‌شود (نه بازنویسیِ منطق)، تا section‌هایِ context-aware
    در پیش‌نمایش هم چیزیِ واقعی و درست-تفکیک‌شده نشان دهند. برایِ سبد،
    دقیقاً همان مسیرِ «سبدِ خالی»یِ ``_cart_context(request, None)`` استفاده
    می‌شود — Preview هرگز نباید سبدِ واقعیِ کاربر را نشان دهد (نگاه کنید
    به ``test_preview_never_shows_real_cart_or_wishlist_count``، Phase 4).
    غیابِ داده (مثلاً فروشگاهی که هنوز هیچ محصولی ندارد) بی‌صدا دیکشنریِ
    خالی برمی‌گرداند — section مربوطه fail-safe چیزی رندر نمی‌کند."""
    if page_type == StorefrontPage.PageType.PRODUCT_DETAIL:
        from apps.catalog.services.product_publish_service import storefront_visible_products
        from apps.catalog.views import build_product_detail_context

        product = storefront_visible_products(store).order_by("-created_at").first()
        return build_product_detail_context(request, product) if product is not None else {}

    if page_type in (StorefrontPage.PageType.LISTING, StorefrontPage.PageType.SEARCH):
        from apps.catalog.views import build_product_listing_context

        return build_product_listing_context(request, store)

    if page_type == StorefrontPage.PageType.COLLECTION:
        from django.core.paginator import Paginator

        from apps.catalog.services import collection_service
        from apps.catalog.views import PRODUCTS_PER_PAGE

        collection = collection_service.public_collection_queryset(store).order_by("-created_at").first()
        if collection is None:
            return {}
        items = collection_service.collection_visible_items(collection, store)
        page_obj = Paginator(items, PRODUCTS_PER_PAGE).get_page(request.GET.get("page"))
        return {"collection": collection, "page_obj": page_obj, "products": [item.product for item in page_obj.object_list]}

    if page_type == StorefrontPage.PageType.CART:
        from apps.cart.views import _cart_context

        return _cart_context(request, None)

    return {}


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

    from . import appearance_registry

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    # Phase 2: پیش‌نمایش هم باید همان صفحه‌ای را نشان دهد که ادیتور در
    # حالِ ویرایشِ آن است — ``?page=`` دقیقاً همان پارامتری است که
    # ``storefront_editor`` به iframe پاس می‌دهد.
    page_type = _resolve_page_type(request.GET.get("page"))
    page = draft.get_page(page_type)
    items = build_page_render_items(page, store, page_context=_preview_page_context(request, store, page_type))
    top_level_categories = Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
    # تنظیماتِ ظاهر باید از همین Draft خوانده شود، نه ShopSettings زنده —
    # نگاه کنید به ``apps.core.context_processors._versioned_colors``.
    #
    # ``?preview_template=<slug>`` (چکپوینتِ «پیش‌نمایشِ غیرمخربِ قالب»)
    # به مرچنت اجازه می‌دهد ظاهرِ یک Templateِ دیگر را در همین iframe
    # ببیند **بدونِ** ذخیره‌شدن روی Draft — فقط همین رندر، هرگز دیتابیس.
    # اسلاگِ نامعتبر/ناشناخته بی‌صدا نادیده گرفته می‌شود (پیش‌نمایشِ
    # Draftِ واقعی، دقیقاً رفتارِ قبل)."""
    preview_template_slug = request.GET.get("preview_template")
    if preview_template_slug and appearance_registry.get_template(preview_template_slug) is not None:
        request.storefront_appearance_version = _CandidateAppearanceVersion(
            draft.effective_appearance_config(), template_slug=preview_template_slug,
        )
    else:
        request.storefront_appearance_version = draft
    return render(request, "storefront_builder/preview.html", {
        "store": store, "version": draft, "page": page, "page_type": page_type,
        "render_items": items, "is_preview": True,
        "top_level_categories": top_level_categories,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_list_partial(request, page_type=None):
    """پارشیال لیست بخش‌ها — برای بازآوری htmx پس از هر تغییر.

    Phase 2: ``page_type`` یا صریحاً توسطِ فراخوانِ Pythonیِ دیگرِ همین
    ماژول پاس داده می‌شود (وقتی آن ویو خودش صفحه‌ی درگیر را از قبل
    می‌داند — مثلاً از رویِ ``section.page``)، یا اگر ``None`` باشد از
    ``page``یِ فرم/querystringِ همینِ درخواست حل می‌شود (وقتی این ویو
    مستقیماً هدفِ یک htmx GET/POST است)."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    if page_type is None:
        page_type = _resolve_page_type(request.POST.get("page") or request.GET.get("page"))
    page = draft.get_page(page_type)
    context = {
        "draft": draft,
        "page_type": page_type,
        "sections": page.sections.order_by("order", "id"),
        "section_definitions": section_registry.list_definitions(),
    }
    return render(request, "dashboard/storefront_builder/partials/section_list.html", context)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_add(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    page_type = _resolve_page_type(request.POST.get("page"))
    page = draft.get_page(page_type)
    section_key = request.POST.get("section_key", "")

    try:
        definition = section_registry.get_definition(section_key)
    except section_registry.UnknownSectionTypeError:
        return HttpResponseBadRequest("نوع بخش نامعتبر است")

    # Phase 5: اجرایِ سمتِ سرورِ allowlistِ نوع‌صفحه — کتابخانه‌ی UI هم
    # صریحاً فیلتر شده (``list_library_groups(page_type=...)``)، اما این
    # چک اینجا تنها نقطه‌ای‌ست که واقعاً رد می‌کند؛ حتی یک POST دستی با
    # section_key معتبر اما نامتناسب با این صفحه باید رد شود.
    if not section_registry.is_section_allowed_on_page(section_key, page_type):
        return HttpResponseBadRequest("این نوع بخش برای این صفحه مجاز نیست")

    existing_count = page.sections.filter(section_key=section_key).count()
    if definition.max_instances is not None and existing_count >= definition.max_instances:
        messages.error(request, f"«{definition.label_fa}» فقط یک بار قابل افزودن است")
        return storefront_section_list_partial(request, page_type=page_type)

    last = page.sections.order_by("-order").first()
    new_order = (last.order + 1) if last else 0
    StorefrontSection.objects.create(
        page=page, section_key=section_key, order=new_order,
        settings=definition.default_settings(),
    )
    messages.success(request, f"«{definition.label_fa}» اضافه شد")
    return storefront_section_list_partial(request, page_type=page_type)


def _get_scoped_section(request, pk):
    """Phase 1A: مسیرِ فیلترِ تفکیکِ مستأجر یک لایه‌یِ ``page__`` عمیق‌تر
    شده (``page__version__...`` به‌جایِ ``version__...`` قبلی) — دقیقاً
    همان دو شرط (فروشگاهِ درست، وضعیتِ Draft)، فقط از طریقِ زنجیره‌یِ
    ارجاعِ جدید."""
    store = _resolve_store(request)
    return get_object_or_404(
        StorefrontSection, pk=pk, page__version__layout__store=store,
        page__version__status=StorefrontLayoutVersion.Status.DRAFT,
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
        elif section.section_key in ("hero_banner", "image_slider"):
            raw = {
                "autoplay": request.POST.get("autoplay") == "on",
                "interval_ms": request.POST.get("interval_ms", ""),
                "show_arrows": request.POST.get("show_arrows") == "on",
                "show_dots": request.POST.get("show_dots") == "on",
                "loop": request.POST.get("loop") == "on",
            }
        elif section.section_key == "category_grid":
            raw = {
                "title": request.POST.get("title", ""),
                "display_mode": request.POST.get("display_mode", ""),
                "category_ids": request.POST.getlist("category_ids"),
            }
        elif section.section_key == "brand_carousel":
            raw = {
                "title": request.POST.get("title", ""),
                "display_mode": request.POST.get("display_mode", ""),
                "show_view_all": request.POST.get("show_view_all") == "on",
                "brand_ids": request.POST.getlist("brand_ids"),
            }
        elif section.section_key == "collection_tiles":
            raw = {
                "title": request.POST.get("title", ""),
                "collection_ids": request.POST.getlist("collection_ids"),
            }
        elif section.section_key == "quick_links":
            raw = {
                "title": request.POST.get("title", ""),
                "menu_id": request.POST.get("menu_id") or None,
            }
        elif section.section_key == "faq":
            questions = request.POST.getlist("question")
            answers = request.POST.getlist("answer")
            raw = {
                "title": request.POST.get("title", ""),
                "items": [{"question": q, "answer": a} for q, a in zip(questions, answers)],
            }
        elif section.section_key == "testimonials":
            names = request.POST.getlist("t_name")
            quotes = request.POST.getlist("t_quote")
            roles = request.POST.getlist("t_role")
            raw = {
                "title": request.POST.get("title", ""),
                "items": [
                    {"name": n, "quote": q, "role": r}
                    for n, q, r in zip(names, quotes, roles)
                ],
            }
        elif section.section_key == "video_section":
            raw = {
                "title": request.POST.get("title", ""),
                "video_url": request.POST.get("video_url", ""),
                "caption": request.POST.get("caption", ""),
            }
        elif section.section_key == "newsletter":
            raw = {
                "title": request.POST.get("title", ""),
                "subtitle": request.POST.get("subtitle", ""),
                "button_label": request.POST.get("button_label", ""),
            }
        else:
            # انواعی که هیچ فیلدِ اختصاصیِ خودشان را ندارند (فازِ D) —
            # تنها چیزی که این فرم برایشان دارد بلوکِ responsive است.
            raw = {}
        raw["responsive"] = _extract_responsive_raw(request, section.section_key)
        if section.section_key in section_registry.DESTINATION_AWARE_SECTION_KEYS:
            raw["destination"] = _extract_destination_raw(request)
        if section.section_key in section_registry.MOTION_AWARE_SECTION_KEYS:
            raw["motion"] = {"style": request.POST.get("motion_style", "none")}
        if section.section_key in section_registry.CARD_AWARE_SECTION_KEYS:
            raw["card"] = _extract_card_raw(request)
        if section.section_key in section_registry.LAYOUT_WIDTH_AWARE_SECTION_KEYS:
            raw["layout"] = _extract_layout_raw(request)
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
        # فقط انواعی که واقعاً چیدمانِ پارامتری دارند کنترلِ «تعدادِ
        # ستون‌ها» را می‌بینند (COLUMN_VISUAL_SECTION_KEYS، نه
        # COLUMN_AWARE_SECTION_KEYS) — طبقِ فیکسِ فازِ D؛ به مستندسازیِ
        # section_registry.py مراجعه شود.
        "supports_columns": section.section_key in section_registry.COLUMN_VISUAL_SECTION_KEYS,
        "supports_card": section.section_key in section_registry.CARD_AWARE_SECTION_KEYS,
        "supports_height": section.section_key in section_registry.LAYOUT_HEIGHT_AWARE_SECTION_KEYS,
    }
    if section.section_key == "product_section":
        context.update(_product_section_picker_context(request, section))
    if section.section_key == "category_grid":
        context.update(_category_grid_picker_context(request, section))
    if section.section_key == "brand_carousel":
        context.update(_brand_carousel_picker_context(request, section))
    if section.section_key == "collection_tiles":
        context.update(_collection_tiles_picker_context(request, section))
    if section.section_key == "quick_links":
        context.update(_quick_links_picker_context(request, section))
    if section.section_key in section_registry.DESTINATION_AWARE_SECTION_KEYS:
        context.update(_destination_picker_context(request, section))
    return render(request, "dashboard/storefront_builder/partials/section_settings_form.html", context)


def _category_grid_picker_context(request, section):
    from apps.catalog.models import Category

    store = _resolve_store(request)
    category_ids = (section.settings or {}).get("category_ids") or []
    categories_by_id = {c.pk: c for c in Category.objects.filter(store=store, pk__in=category_ids)}
    return {
        "all_categories": Category.objects.filter(store=store, is_active=True).order_by("name"),
        "initial_selected_categories": [
            {"id": cid, "name": categories_by_id[cid].name} for cid in category_ids if cid in categories_by_id
        ],
    }


def _brand_carousel_picker_context(request, section):
    from apps.catalog.models import Brand

    store = _resolve_store(request)
    brand_ids = (section.settings or {}).get("brand_ids") or []
    brands_by_id = {b.pk: b for b in Brand.objects.filter(store=store, pk__in=brand_ids)}
    return {
        "all_brands": Brand.objects.filter(store=store, is_active=True).order_by("name"),
        "initial_selected_brands": [
            {"id": bid, "name": brands_by_id[bid].name} for bid in brand_ids if bid in brands_by_id
        ],
    }


def _collection_tiles_picker_context(request, section):
    from apps.catalog.models import MerchantCollection

    store = _resolve_store(request)
    collection_ids = (section.settings or {}).get("collection_ids") or []
    collections_by_id = {c.pk: c for c in MerchantCollection.objects.filter(store=store, pk__in=collection_ids)}
    return {
        "all_collections": MerchantCollection.objects.filter(store=store, is_active=True).order_by("name"),
        "initial_selected_collections": [
            {"id": cid, "name": collections_by_id[cid].name} for cid in collection_ids if cid in collections_by_id
        ],
    }


def _quick_links_picker_context(request, section):
    from apps.content.models import Menu

    store = _resolve_store(request)
    return {"all_menus": Menu.objects.filter(store=store, is_active=True).order_by("title")}


def _extract_destination_raw(request) -> dict:
    """بلوکِ خامِ «لینک این بخش» را از POST می‌خواند — یک بار نوشته شده،
    توسطِ هر نوع سکشنِ عضوِ ``DESTINATION_AWARE_SECTION_KEYS`` استفاده
    می‌شود. فرمِ ادیتور یک ``<select name="destination_type">`` مشترک دارد
    و بسته به مقدارش، یکی از چهار فیلدِ ``destination_*_id`` را پر می‌کند —
    اینجا همان یکیِ متناظر با نوعِ انتخاب‌شده به ``destination_id`` عمومی
    نگاشت می‌شود."""
    dtype = request.POST.get("destination_type", "none")
    id_field_by_type = {
        "category": "destination_category_id",
        "brand": "destination_brand_id",
        "collection": "destination_collection_id",
        "product": "destination_product_id",
    }
    destination_id = None
    if dtype in id_field_by_type:
        destination_id = request.POST.get(id_field_by_type[dtype]) or None
    return {
        "destination_type": dtype,
        "destination_id": destination_id,
        "destination_external_url": request.POST.get("destination_external_url", ""),
        "open_in_new_tab": request.POST.get("open_in_new_tab") == "on",
    }


def _destination_picker_context(request, section) -> dict:
    """کالکشن‌ها/دسته‌بندی‌ها/برندهایِ همین Store برایِ کشوهای انتخابِ
    مقصدِ بلوکِ ``destination`` + نامِ محصولِ فعلاً انتخاب‌شده (اگر
    destination_type فعلی «محصول» باشد) برایِ نمایشِ اولیه — دقیقاً همان
    الگویِ ``_product_section_picker_context`` بالا، عمداً جداگانه چون
    قراردادِ ``destination`` عمومی‌تر (برایِ هر نوع section) است."""
    from apps.catalog.models import Brand, Category, MerchantCollection, Product

    store = _resolve_store(request)
    dest = (section.settings or {}).get("destination") or {}
    product_name = ""
    if dest.get("destination_type") == "product" and dest.get("destination_id"):
        product = Product.objects.filter(store=store, pk=dest["destination_id"]).first()
        product_name = product.name if product else ""
    return {
        "collections": MerchantCollection.objects.filter(store=store).order_by("name"),
        "categories": Category.objects.filter(store=store).order_by("name"),
        "brands": Brand.objects.filter(store=store).order_by("name"),
        "destination_product_name": product_name,
    }


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
    # عمداً روی مجموعه‌ی عمومی‌ترِ COLUMN_AWARE_SECTION_KEYS (نه
    # COLUMN_VISUAL_SECTION_KEYSِ محدودترِ بالا) — قراردادِ ذخیره‌سازی
    # باید عمومی/آینده‌نگر بماند؛ برایِ چهار نوعی که فعلاً کنترلِ UI
    # ندارند، این فیلدها صرفاً در POST حاضر نیستند و
    # validate_responsive_settings به‌طورِ امن پیش‌فرض را جایگزین می‌کند.
    if section_key in section_registry.COLUMN_AWARE_SECTION_KEYS:
        raw["desktop_columns"] = request.POST.get("desktop_columns")
        raw["tablet_columns"] = request.POST.get("tablet_columns")
        raw["mobile_columns"] = request.POST.get("mobile_columns")
    return raw


def _extract_card_raw(request) -> dict:
    """Phase 8 P0-2 — بلوکِ خامِ «ظاهرِ کارتِ محصول» را از POST می‌خواند،
    فقط برایِ ``CARD_AWARE_SECTION_KEYS``. دقیقاً همان الگویِ
    ``_extract_responsive_raw``: تیک‌های مثبت («نمایشِ …») مستقیم به
    کلیدهایِ ``show_*`` تبدیل می‌شوند (بدونِ وارونگیِ منفی، چون خودِ
    ``validate_card_settings`` هم مثبت است)."""
    return {
        "show_brand": request.POST.get("card_show_brand") == "on",
        "show_price": request.POST.get("card_show_price") == "on",
        "show_badge": request.POST.get("card_show_badge") == "on",
        "show_wishlist": request.POST.get("card_show_wishlist") == "on",
        "show_quick_add": request.POST.get("card_show_quick_add") == "on",
        "card_border": request.POST.get("card_border") == "on",
        "image_ratio": request.POST.get("card_image_ratio", "square"),
        "quick_add_reveal": request.POST.get("card_quick_add_reveal", "hover_slide"),
    }


def _extract_layout_raw(request) -> dict:
    """Phase 8 P0-5 — بلوکِ خامِ «اندازه‌ی بخش» (عرض/ارتفاع) را از POST
    می‌خواند، فقط برایِ ``LAYOUT_WIDTH_AWARE_SECTION_KEYS``. کلیدِ
    ``height`` حتی برایِ انواعی که ارتفاع پشتیبانی نمی‌شود بی‌ضرر
    فرستاده می‌شود — ``validate_layout_settings`` آن را بر اساسِ
    ``supports_height`` نادیده می‌گیرد."""
    return {
        "content_width": request.POST.get("layout_content_width", "standard"),
        "height": request.POST.get("layout_height", "standard"),
    }


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
    query = (request.GET.get("q") or request.GET.get("q_dest_product") or "").strip()
    results = collection_service.searchable_products(store, query=query)[:20] if query else []
    return render(request, "dashboard/storefront_builder/partials/product_section_search_results.html", {
        "results": results, "query": query, "mode": request.GET.get("mode", ""),
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_remove(request, pk):
    section = _get_scoped_section(request, pk)
    page_type = section.page.page_type
    # Phase 1 (spec §37 — Lock): «It cannot be deleted» — چک می‌شود پیش از
    # چکِ removable نوعِ section (اگر هر دو نقض شده باشند، تاجر پیامِ
    # قفل‌بودن را می‌بیند، چون آن یک تصمیمِ per-instance و آگاهانه‌تر است).
    if section.is_locked:
        messages.error(request, "این بخش قفل است — ابتدا قفل آن را باز کنید")
        return storefront_section_list_partial(request, page_type=page_type)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.removable:
            messages.error(request, f"«{definition.label_fa}» قابل حذف نیست")
            return storefront_section_list_partial(request, page_type=page_type)
    except section_registry.UnknownSectionTypeError:
        pass
    section.delete()
    messages.success(request, "بخش حذف شد")
    return storefront_section_list_partial(request, page_type=page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_toggle(request, pk):
    section = _get_scoped_section(request, pk)
    section.is_active = not section.is_active
    section.save(update_fields=["is_active", "updated_at"])
    return storefront_section_list_partial(request, page_type=section.page.page_type)


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
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_lock_toggle(request, pk):
    """قفل/بازکردنِ یک بخش — Phase 1 (spec §37). دقیقاً همان الگویِ
    ``storefront_section_collapse_toggle``؛ خودِ اثرِ قفل‌بودن (منعِ حذف/
    جابه‌جایی) در ``storefront_section_remove``/``storefront_section_move``
    اعمال می‌شود، نه اینجا — این view فقط پرچم را toggle می‌کند."""
    section = _get_scoped_section(request, pk)
    section.is_locked = not section.is_locked
    section.save(update_fields=["is_locked", "updated_at"])
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_duplicate(request, pk):
    """تکرارِ یک بخش — یک بخشِ منطقیِ **جدید** می‌سازد.

    Phase 0.5 (تصمیمِ مالک ۳/۹): برخلافِ کلونِ نسخه (که ``stable_id`` را
    حفظ می‌کند چون همان بخشِ منطقی است)، تکرار عمداً یک ``stable_id`` تازه
    می‌گیرد (پیش‌فرضِ فیلد — ``uuid.uuid4()``، نه چیزی که اینجا صریحاً
    ست شود) — این یک بخشِ منطقیِ کاملاً جدید و مستقل است.

    اگر بخشِ منبع رسانه‌یِ section-scoped (HeroSlide/PromotionalBanner/
    StoryRailItem) داشته باشد، آن هم تکرار می‌شود — Placementهایِ جدید به
    **همان** ``MediaAsset``هایِ منبع اشاره می‌کنند (بدونِ کپیِ بایتِ فایل)،
    اما تنظیماتِ خودشان (عنوان/دکمه/مقصد/ترتیب) به‌طورِ کاملاً مستقل کپی
    می‌شود — ویرایشِ بعدیِ Placementِ تکرارشده هرگز روی Placementِ منبع
    اثر نمی‌گذارد (همان الگویِ استقلالِ ``settings`` که از قبل برایِ خودِ
    section وجود داشت)."""
    section = _get_scoped_section(request, pk)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.duplicable:
            messages.error(request, f"«{definition.label_fa}» قابل تکرار نیست")
            return storefront_section_list_partial(request, page_type=section.page.page_type)
    except section_registry.UnknownSectionTypeError:
        pass
    # Phase 1A: تکرار همیشه رویِ **همان صفحه‌ای** که section بهش تعلق
    # دارد اتفاق می‌افتد (``section.page``، نه ``section.version.home_page()``
    # که اگر section از یک صفحه‌ی غیرِ اصلی باشد اشتباه می‌بود) — از
    # Phase 2 (سازنده‌ی تک‌صفحه‌ای) به بعد، ادیتور واقعاً رویِ هر شش صفحه
    # کار می‌کند، پس این نوشتار دیگر صرفاً یک احتیاطِ آینده‌نگر نیست.
    last = section.page.sections.order_by("-order").first()
    new_order = (last.order + 1) if last else 0
    new_section = StorefrontSection.objects.create(
        page=section.page, section_key=section.section_key,
        order=new_order, is_active=section.is_active, settings=dict(section.settings or {}),
        # stable_id عمداً اینجا پاس داده نمی‌شود — پیش‌فرضِ فیلد
        # (``uuid.uuid4``) خودش یک شناسه‌ی منطقیِ تازه تولید می‌کند.
    )
    _clone_section_scoped_media(section, new_section)
    messages.success(request, "بخش تکرار شد")
    return storefront_section_list_partial(request, page_type=section.page.page_type)


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
    page_type = _resolve_page_type(request.POST.get("page"))
    page = draft.get_page(page_type)
    section_ids = request.POST.getlist("section_ids")

    valid_ids = set(page.sections.values_list("pk", flat=True))
    ordered_ids = [int(i) for i in section_ids if i.isdigit() and int(i) in valid_ids]

    if len(set(ordered_ids)) != len(ordered_ids):
        messages.error(request, "فهرست مرتب‌سازی شامل شناسه‌ی تکراری است — ترتیب تغییر نکرد")
        return storefront_section_list_partial(request, page_type=page_type)

    with transaction.atomic():
        for index, section_id in enumerate(ordered_ids):
            StorefrontSection.objects.filter(pk=section_id, page=page).update(order=index)

    return storefront_section_list_partial(request, page_type=page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_move(request, pk):
    """جابه‌جایی یک بخش به بالا/پایین — fallback برای موبایل/کیبورد وقتی
    drag-and-drop عملی نیست."""
    direction = request.POST.get("direction")
    section = _get_scoped_section(request, pk)
    # Phase 1 (spec §37 — Lock): «It cannot be moved».
    if section.is_locked:
        messages.error(request, "این بخش قفل است — ابتدا قفل آن را باز کنید")
        return storefront_section_list_partial(request, page_type=section.page.page_type)
    # Phase 1A: جابه‌جایی همیشه بینِ خواهر-وبرادرهایِ **همان صفحه** انجام
    # می‌شود (``section.page.sections``، نه ``section.version.sections``ی
    # تجمیعیِ همه‌ی صفحات که خواهر-وبرادرهایِ صفحاتِ دیگر را هم قاطی
    # می‌کرد).
    siblings = list(section.page.sections.order_by("order", "id"))
    index = next((i for i, s in enumerate(siblings) if s.pk == section.pk), None)
    if index is None:
        return storefront_section_list_partial(request)

    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(siblings):
        other = siblings[swap_index]
        section.order, other.order = other.order, section.order
        StorefrontSection.objects.bulk_update([section, other], ["order"])
    return storefront_section_list_partial(request, page_type=section.page.page_type)


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
def storefront_apply_layout_preset(request):
    """اعمالِ یکی از چهار Preset درون‌ساختِ V2 (``layout_preset_registry``)
    روی Draftِ فعلی — Phase 6. کاملاً مستقل از فرمِ Family/Template/Palette
    در ``storefront_appearance_editor`` (همان ویو دست‌نخورده می‌ماند)؛
    عمداً یک ویویِ جدا با همان قراردادِ ``storefront_apply_industry_layout``:
    اگر هرکدام از صفحاتی که این Preset پوشش می‌دهد از قبل Sectionی دارند،
    بدونِ ``confirm_preset_apply=1`` (تأییدِ صریحِ کاربر در UI) رد می‌شود."""
    from . import layout_preset_registry
    from .services import preset_service

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    key = request.POST.get("preset_key")
    preset = layout_preset_registry.get_layout_preset(key)
    if preset is None:
        messages.error(request, "پیش‌تنظیمِ انتخاب‌شده یافت نشد")
        return redirect("dashboard:storefront-builder-editor")

    would_replace = any(
        draft.get_page(page_type).sections.exists() for page_type in preset.pages
    )
    if would_replace and request.POST.get("confirm_preset_apply") != "1":
        messages.error(
            request,
            "اعمالِ این پیش‌تنظیم، چیدمانِ صفحاتِ پوشش‌داده‌شده در پیش‌نویسِ فعلی را جایگزین می‌کند — "
            "برای ادامه، تأیید صریح لازم است",
        )
        return redirect("dashboard:storefront-builder-editor")

    try:
        preset_service.apply_preset(draft, preset)
        messages.success(request, f"پیش‌تنظیمِ «{preset.label_fa}» اعمال شد")
    except preset_service.InvalidPresetError as exc:
        messages.error(request, str(exc))
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
def storefront_appearance_editor(request):
    """پنلِ «ظاهر سایت» — هابِ Template/Palette/رنگ‌های سفارشی/فونت و
    گردی/تراکم/حرکت. برخلافِ هدر/فوتر (صفحه‌ی کاملاً جدا)، این پنل به
    htmx داخلِ همان صفحه‌ی سازنده بارگذاری می‌شود (طبقِ الزامِ صریحِ کار:
    «مرچنت نباید مجبور شود از سازنده بصری خارج شود») — نگاه کنید به
    ``editor.html`` (تبِ «ظاهر سایت»)."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        from . import appearance_registry

        current = draft.effective_appearance_config()

        new_template_slug = request.POST.get("template_slug", current["template_slug"])
        template_changed = new_template_slug != current.get("template_slug")
        new_template = appearance_registry.get_template(new_template_slug) if template_changed else None

        # تعویضِ Palette یعنی شروعِ تازه — override هایِ پالتِ قبلی روی
        # پالتِ جدید بی‌معنا/گیج‌کننده‌اند (طبقِ الزامِ صریحِ کار: انتخابِ
        # پالت یعنی «تمامِ رنگ‌های هماهنگ با هم تغییر کنند»).
        posted_palette_slug = request.POST.get("palette_slug")
        new_palette_slug = posted_palette_slug if posted_palette_slug else current.get("palette_slug")
        palette_changed = new_palette_slug != current.get("palette_slug")
        color_overrides = {} if palette_changed else dict(current.get("color_overrides") or {})

        def _field(name):
            # اولویتِ منبعِ فیلدهایِ ساختاری: Templateِ قدیمی (اگر Template
            # همین الان تغییر کرده) > مقدارِ پست‌شده > مقدارِ فعلی.
            if new_template is not None:
                return getattr(new_template, name)
            return request.POST.get(name, current[name])

        raw = {
            "template_slug": new_template_slug,
            "palette_slug": new_palette_slug,
            "color_overrides": color_overrides,
            "font": _field("font"),
            "radius": _field("radius"),
            "button_radius": _field("button_radius"),
            "density": _field("density"),
            "motion": _field("motion"),
            "type_scale": _field("type_scale"),
            "button_style": _field("button_style"),
            # رفتارِ تصویر — همیشه مستقیماً از فرمِ مرچنت خوانده می‌شود،
            # حتی وقتی تعویضِ Template هم در همین POST رخ داده باشد
            # (هیچ Templateای چنین فیلدی ندارد).
            "image_fit": request.POST.get("image_fit", current["image_fit"]),
            "image_hover": request.POST.get("image_hover", current["image_hover"]),
            "card_image_crossfade": (request.POST.get("card_image_crossfade", "") == "1" if "card_image_crossfade" in request.POST else current.get("card_image_crossfade", False)),
            "card_image_zoom": (request.POST.get("card_image_zoom", "") == "1" if "card_image_zoom" in request.POST else current.get("card_image_zoom", True)),
            # Phase 8 P0-7 — این ۵ فیلد اختیاری‌اند (نه بخشی از
            # APPEARANCE_CONFIG_DEFAULTS)؛ اگر فرمِ POSTکننده آن‌ها را
            # حمل نکند (مثلاً یک فرمِ قدیمی‌تر)، به مقدارِ فعلیِ ذخیره‌شده
            # برمی‌گردیم، نه به یک پیش‌فرضِ سخت‌کدشده.
            "content_width": request.POST.get("content_width", current.get("content_width")),
            "grid_density": request.POST.get("grid_density", current.get("grid_density")),
            "card_shadow": request.POST.get("card_shadow", current.get("card_shadow")),
            "card_hover": request.POST.get("card_hover", current.get("card_hover")),
            "hero_style": request.POST.get("hero_style", current.get("hero_style")),
        }
        from .models import APPEARANCE_COLOR_KEYS

        reset_key = request.POST.get("reset_color")
        if request.POST.get("reset_all_overrides") == "1":
            # بازگردانیِ کلِ پالت — کلِ override ها پاک می‌شود، حتی اگر
            # فیلدهایِ رنگِ دیگر هم در همین POST حاضر باشند (چون همان
            # فرمِ خودِ صفحه‌ی رنگ‌هاست) — این دکمه عمداً هر ادعایِ دیگری
            # را نادیده می‌گیرد.
            raw["color_overrides"] = {}
        elif reset_key:
            # بازگردانیِ *فقط یک* رنگ — عمداً بقیه‌ی فیلدهایِ ``color_*``ی
            # همین POST را نادیده می‌گیرد (آن‌ها فقط مقدارِ نمایشیِ فعلیِ
            # input رنگی‌اند، نه تغییرِ واقعیِ مرچنت) وگرنه همان لحظه با
            # مقدارِ فعلی دوباره override می‌شدند و «بازگردانی» بی‌اثر
            # می‌ماند.
            raw["color_overrides"].pop(reset_key, None)
        else:
            for color_key in APPEARANCE_COLOR_KEYS:
                posted = request.POST.get(f"color_{color_key}")
                if posted:
                    raw["color_overrides"][color_key] = posted
        try:
            config = layout_service.validate_appearance_config(raw)
        except layout_service.AppearanceConfigValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:storefront-builder-editor")
        draft.appearance_config = config
        draft.save(update_fields=["appearance_config", "updated_at"])
        messages.success(request, "تنظیمات ظاهر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    from . import appearance_registry, layout_preset_registry

    config = draft.effective_appearance_config()
    color_field_labels = [
        ("primary", "رنگ اصلی"), ("secondary", "رنگ مکمل"), ("accent", "رنگ تأکیدی"),
        ("background", "پس‌زمینه"), ("surface", "سطح و کارت‌ها"), ("text", "متن اصلی"),
        ("muted", "متن کم‌رنگ"), ("border", "حاشیه‌ها"),
    ]
    return render(request, "dashboard/storefront_builder/partials/appearance_panel.html", {
        "draft": draft,
        "config": config,
        "resolved_colors": appearance_registry.resolve_colors(config),
        "palettes": appearance_registry.list_palettes(),
        "templates": appearance_registry.list_templates(),
        "font_choices": appearance_registry.FONT_CHOICES,
        "density_choices": appearance_registry.DENSITY_CHOICES,
        "motion_choices": appearance_registry.MOTION_CHOICES,
        "type_scale_choices": appearance_registry.TYPE_SCALE_CHOICES,
        "button_style_choices": appearance_registry.BUTTON_STYLE_CHOICES,
        "image_fit_choices": appearance_registry.IMAGE_FIT_CHOICES,
        "image_hover_choices": appearance_registry.IMAGE_HOVER_CHOICES,
        "color_field_labels": color_field_labels,
        "site_content_width_choices": appearance_registry.SITE_CONTENT_WIDTH_CHOICES,
        "site_grid_density_choices": appearance_registry.SITE_GRID_DENSITY_CHOICES,
        "site_card_shadow_choices": appearance_registry.SITE_CARD_SHADOW_CHOICES,
        "site_card_hover_choices": appearance_registry.SITE_CARD_HOVER_CHOICES,
        "site_hero_style_choices": appearance_registry.SITE_HERO_STYLE_CHOICES,
        # Phase 6 — چهار Preset درون‌ساختِ V2؛ کاملاً مستقل از Family/
        # Template/Palette بالا (نگاه کنید به ``layout_preset_registry.py``).
        "layout_presets": layout_preset_registry.list_layout_presets(),
        "active_layout_preset_key": config.get("layout_preset_key"),
    })


def _extract_shell_responsive_raw(request, keys: list[str]) -> dict:
    """بلوکِ خامِ «نمایش در دستگاه‌ها»یِ هدر/فوتر را از POST می‌خواند —
    Phase 4، معادلِ ``_extract_responsive_raw`` سطحِ section اما با
    قراردادِ نام‌گذاریِ مستقیم (``{key}__hide_on_tablet``) چون چک‌باکسِ
    UI اینجا خودش «پنهان در ...» است، نه «نمایش در ...» (پس نیازی به
    وارونه‌سازیِ مضاعف نیست)."""
    return {
        key: {
            "hide_on_tablet": request.POST.get(f"{key}__hide_on_tablet") == "on",
            "hide_on_mobile": request.POST.get(f"{key}__hide_on_mobile") == "on",
        }
        for key in keys
    }


def _extract_header_extra_blocks_raw(request) -> list[dict]:
    """Phase 8 P0-3 — بلوک‌هایِ اختیاریِ هدر (تلفن/شبکه‌ی اجتماعی/CTA/
    فاصله) را از سه فهرستِ POSTِ موازی می‌خواند — دقیقاً همان الگویِ
    itemRepeaterFormِ از‌قبل‌موجود (FAQ/نظراتِ مشتریان، ``editor.html``):
    ترتیبِ سه فهرست، ترتیبِ بلوک‌هاست."""
    types = request.POST.getlist("block_type")
    labels = request.POST.getlist("block_label")
    urls = request.POST.getlist("block_url")
    blocks = []
    for i, block_type in enumerate(types):
        block = {"type": block_type}
        if block_type == "cta":
            block["label"] = labels[i] if i < len(labels) else ""
            block["url"] = urls[i] if i < len(urls) else ""
        blocks.append(block)
    return blocks


def _extract_footer_extra_blocks_raw(request) -> list[dict]:
    """Phase 8 P0-4 — ستون‌هایِ اضافیِ فوتر (متنِ دلخواه/لینک/شبکه‌ی
    اجتماعیِ تکراری) را از سه فهرستِ POSTِ موازی می‌خواند — همان الگویِ
    ``_extract_header_extra_blocks_raw`` بالا."""
    types = request.POST.getlist("footer_block_type")
    titles = request.POST.getlist("footer_block_title")
    texts = request.POST.getlist("footer_block_text")
    labels = request.POST.getlist("footer_block_label")
    urls = request.POST.getlist("footer_block_url")
    blocks = []
    for i, block_type in enumerate(types):
        block = {"type": block_type}
        if block_type == "custom_text":
            block["title"] = titles[i] if i < len(titles) else ""
            block["text"] = texts[i] if i < len(texts) else ""
        elif block_type == "link":
            block["label"] = labels[i] if i < len(labels) else ""
            block["url"] = urls[i] if i < len(urls) else ""
        blocks.append(block)
    return blocks


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_header_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        raw = {field: request.POST.get(field) == "on" for field in HEADER_TOGGLE_FIELDS}
        raw["announcement_text"] = request.POST.get("announcement_text", "")
        raw["responsive"] = _extract_shell_responsive_raw(request, HEADER_RESPONSIVE_AWARE_KEYS)
        raw["extra_blocks"] = _extract_header_extra_blocks_raw(request)
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

    template_name = (
        "dashboard/storefront_builder/partials/header_panel.html"
        if request.headers.get("HX-Request") == "true"
        else "dashboard/storefront_builder/header_editor.html"
    )
    return render(request, template_name, {
        "active_page": "storefront_builder", "config": draft.effective_header_config(), "draft": draft,
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_footer_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        raw = {field: request.POST.get(field) == "on" for field in FOOTER_TOGGLE_FIELDS}
        raw["responsive"] = _extract_shell_responsive_raw(request, FOOTER_RESPONSIVE_AWARE_KEYS)
        raw["extra_blocks"] = _extract_footer_extra_blocks_raw(request)
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

    template_name = (
        "dashboard/storefront_builder/partials/footer_panel.html"
        if request.headers.get("HX-Request") == "true"
        else "dashboard/storefront_builder/footer_editor.html"
    )
    return render(request, template_name, {
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
