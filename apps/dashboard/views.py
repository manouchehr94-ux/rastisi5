import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, ProtectedError, Q, Sum, prefetch_related_objects
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.catalog.models import (
    Attribute,
    AttributeValue,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
)
from apps.catalog.services.attribute_service import (
    AttributeError_,
    AttributeInUseError,
    activate_attribute,
    archive_attribute,
    archive_attribute_value,
    can_delete_attribute,
    can_delete_attribute_value,
    create_attribute,
    create_attribute_value,
    delete_attribute,
    delete_attribute_value,
    update_attribute,
    update_attribute_value,
)
from apps.catalog.services.pricing_service import resolve_effective_price
from apps.catalog.services.product_image_service import (
    ProductImageError,
    add_product_image,
    delete_product_image,
    move_product_image,
    set_cover_image,
    set_image_variant,
    update_image_alt,
)
from apps.catalog.services.variant_engine_service import (
    VariantEngineError,
    add_option_value,
    add_product_option,
    activate_product_option,
    deactivate_product_option,
    generate_variants,
    preview_combination_count,
    remove_option_value,
    reorder_product_options,
    set_default_variant,
)
from apps.catalog.services.variant_service import (
    ProductTypeError,
    VariantError,
    bulk_create_variants,
    deactivate_variant,
    delete_variant,
    parse_bulk_values,
    reorder_variants,
    set_product_type,
    update_variant,
)
from apps.core.color_utils import safe_hex
from apps.core.utils import normalize_digits
from apps.core.models import ShopSettings
from apps.core.theme_presets import THEME_PRESETS, matching_preset_key
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, Transaction
from apps.orders.services.order_service import change_order_status
from apps.sms.events import EVENT_VARIABLES
from apps.sms.models import SmsTemplate
from apps.sms.services.sms_service import SmsTemplateError, send_test_sms

from .decorators import admin_host_required, permission_required, staff_required
from apps.stores.authorization import (
    ATTRIBUTE_MANAGE,
    CATEGORY_MANAGE,
    CONTENT_MANAGE,
    CUSTOMER_VIEW,
    DASHBOARD_VIEW,
    MEDIA_MANAGE,
    ORDER_STATUS_CHANGE,
    ORDER_VIEW,
    PAYMENT_SETTINGS_MANAGE,
    PRODUCT_CREATE,
    PRODUCT_DELETE,
    PRODUCT_EDIT,
    PRODUCT_VIEW,
    REPORTS_VIEW,
    SETTINGS_MANAGE,
    SMS_SETTINGS_MANAGE,
    VARIANT_MANAGE,
    membership_has_permission,
)
from .forms import (
    AttributeForm,
    AttributeValueForm,
    CategoryEditForm,
    FinanceSettingsForm,
    MainCategoryForm,
    ProductForm,
    ProductImageAltForm,
    ProductImageUploadForm,
    ProductOptionForm,
    ProductOptionValueAddForm,
    ShopInfoForm,
    SmsConnectionForm,
    SmsTemplateForm,
    SmsTestForm,
    SubCategoryForm,
    VariantBulkAddForm,
    VariantEditForm,
    VisualIdentityForm,
)
from .services import (
    customers_admin_service,
    dashboard_service,
    report_service,
    settings_admin_service,
    sms_admin_service,
)
from .services.catalog_admin_service import (
    BULK_STATUS_ACTIONS,
    DEFAULT_PRODUCT_SORT,
    PRODUCT_SORT_OPTIONS,
    PRODUCT_STATUS_FILTERS,
    BulkActionError,
    CategoryDeleteError,
    bulk_assign_category,
    bulk_delete_products,
    bulk_set_product_status,
    can_delete_category,
    category_tree_context,
    default_vendor,
    filtered_products,
    generate_unique_slug,
    leaf_categories,
)
from .services.charts import build_line_chart_svg
from .services.orders_admin_service import (
    INVOICE_STATUS_FILTERS,
    ORDER_STATUS_FILTERS,
    TRANSACTION_STATUS_FILTERS,
    filtered_invoices,
    filtered_orders,
    filtered_transactions,
    invoice_totals,
    next_status_options,
    order_is_final,
    order_status_counts,
    order_status_steps,
)

VALID_RANGES = {"week", "month", "year"}


@admin_host_required
def admin_login(request):
    """صفحه‌ی ورود اختصاصی پنل مدیریت — مستقل از فروشگاه، اما هنوز هم فقط
    روی میزبان مدیریت مجاز قابل‌دسترسی (نگاه کنید به ``admin_host_required``)."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(request.GET.get("next", "/admin-portal/"))

    error = ""
    username = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            auth_login(request, user)
            next_url = request.POST.get("next", request.GET.get("next", "/admin-portal/"))
            # Prevent open redirect — ensure next is a relative admin path
            if not next_url.startswith("/admin-portal/"):
                next_url = "/admin-portal/"
            return redirect(next_url)
        elif user is not None and not user.is_staff:
            error = "شما به پنل مدیریت دسترسی ندارید"
        else:
            error = "نام کاربری یا رمز عبور اشتباه است"

    next_url = request.GET.get("next", "/admin-portal/")
    return render(request, "dashboard/login.html", {
        "error": error,
        "username": username,
        "next": next_url,
    })


@staff_required
@permission_required(DASHBOARD_VIEW)
def dashboard_home(request):
    store = _resolve_dashboard_store(request)
    context = dashboard_service.build_dashboard_context(store)
    context["active_page"] = "dashboard"
    return render(request, "dashboard/dashboard.html", context)


@staff_required
@permission_required(DASHBOARD_VIEW)
def sales_chart_partial(request):
    store = _resolve_dashboard_store(request)
    range_key = request.GET.get("range", "month")
    if range_key not in VALID_RANGES:
        range_key = "month"
    data, labels = dashboard_service.sales_chart_data(store, range_key)
    svg = build_line_chart_svg(data, labels)
    return render(request, "dashboard/partials/sales_chart.html", {"svg": svg})


# ---------------------------------------------------------------- محصولات

PRODUCTS_PER_PAGE = 20


def _product_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    brand_id = request.GET.get("brand", "")
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", DEFAULT_PRODUCT_SORT)
    if sort not in PRODUCT_SORT_OPTIONS:
        sort = DEFAULT_PRODUCT_SORT

    qs = filtered_products(store, q=q, category_id=category_id, status=status, brand_id=brand_id, sort=sort)
    paginator = Paginator(qs, PRODUCTS_PER_PAGE)
    page_number = request.GET.get("page", "1")
    page_obj = paginator.get_page(page_number)

    return {
        "products": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q,
        "selected_category": category_id,
        "selected_brand": brand_id,
        "selected_status": status,
        "selected_sort": sort,
        "category_options": leaf_categories(store),
        "brand_options": Brand.objects.filter(store=store).order_by("name"),
        "status_options": PRODUCT_STATUS_FILTERS,
        "sort_options": [(key, label) for key, (_fields, label) in PRODUCT_SORT_OPTIONS.items()],
    }


@staff_required
@permission_required(PRODUCT_VIEW)
def product_list(request):
    context = _product_list_context(request)
    context["active_page"] = "products"
    return render(request, "dashboard/products.html", context)


@staff_required
@permission_required(PRODUCT_VIEW)
def product_table(request):
    return render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))


def _selected_product_ids(request):
    ids = request.POST.getlist("product_ids")
    valid = []
    for raw in ids:
        try:
            valid.append(int(raw))
        except (TypeError, ValueError):
            continue
    return valid


@require_POST
@staff_required
def product_bulk_action(request):
    """اکشن فله‌ای روی کالاهای انتخاب‌شده — فقط کالاهای همین Store، هرگز بر
    اساس اعتماد به شناسه‌های ارسالی بدون فیلتر Store (نگاه کنید به
    ``catalog_admin_service.bulk_*``). مجوز لازم بسته به نوع اکشن فرق دارد:
    تغییر وضعیت/دسته‌بندی نیازمند PRODUCT_EDIT، حذف نیازمند PRODUCT_DELETE."""
    store = _resolve_dashboard_store(request)
    action = request.POST.get("bulk_action", "")
    product_ids = _selected_product_ids(request)

    required_permission = PRODUCT_DELETE if action == "delete" else PRODUCT_EDIT
    if not membership_has_permission(request.store_membership, required_permission):
        return render(request, "dashboard/403.html", status=403)

    if not product_ids:
        messages.warning(request, "هیچ کالایی انتخاب نشده است")
    else:
        try:
            if action in BULK_STATUS_ACTIONS:
                count = bulk_set_product_status(store, product_ids, action)
                messages.success(request, f"وضعیت {count} کالا به‌روزرسانی شد")
            elif action == "delete":
                count = bulk_delete_products(store, product_ids)
                messages.success(request, f"{count} کالا حذف شد")
            elif action == "assign-category":
                category_id = request.POST.get("bulk_category", "")
                count = bulk_assign_category(store, product_ids, category_id)
                messages.success(request, f"دسته‌بندی {count} کالا به‌روزرسانی شد")
            else:
                messages.error(request, "اکشن فله‌ای نامعتبر است")
        except BulkActionError as exc:
            messages.error(request, str(exc))

    return render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))


class NoVendorForStoreError(Exception):
    """این Store هنوز هیچ فروشنده‌ای ندارد؛ کالای جدید بدون فروشنده قابل ساخت نیست."""


def _save_product(form, product, *, store):
    data = form.cleaned_data
    if product is None:
        vendor = default_vendor(store)
        if vendor is None:
            raise NoVendorForStoreError(
                "برای این فروشگاه هنوز هیچ فروشنده‌ای ثبت نشده است؛ ابتدا یک فروشنده بسازید."
            )
        product = Product(store=store, vendor=vendor)
        product.slug = generate_unique_slug(Product, data["name"], store=store)
    product.name = data["name"]
    product.sku = data["sku"]
    product.category = data["category"]
    product.brand = data.get("brand")
    product.price = data["price"]
    product.discount_percent = data["discount_percent"]
    product.stock = data["stock"]
    product.status = data["status"]
    product.icon = data["icon"] or "🛍️"
    product.description = data["description"]
    product.barcode = data.get("barcode") or ""
    product.weight_grams = data.get("weight_grams")
    product.requires_shipping = data.get("requires_shipping", True)
    product.seo_title = data.get("seo_title") or ""
    product.seo_description = data.get("seo_description") or ""
    product.full_clean(exclude=["slug"])
    product.save()
    return product


@staff_required
@permission_required(PRODUCT_CREATE, PRODUCT_EDIT)
def product_form(request, pk=None):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    is_new = product is None

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product, store=store)
        if form.is_valid():
            requested_type = form.cleaned_data.get("product_type") or None
            try:
                with transaction.atomic():
                    product = _save_product(form, product, store=store)
                    if requested_type and requested_type != product.product_type:
                        set_product_type(product, requested_type)
            except (ProductTypeError, NoVendorForStoreError) as exc:
                form.add_error(None, str(exc))
                return render(request, "dashboard/partials/product_form.html", {"form": form, "product": product})
            except ValidationError as exc:
                for field, messages in exc.message_dict.items():
                    for message in messages:
                        form.add_error(field if field in form.fields else None, message)
                return render(request, "dashboard/partials/product_form.html", {"form": form, "product": product})

            table_html = render_to_string(
                "dashboard/partials/products_table_inner.html", _product_list_context(request), request=request,
            )
            response = render(request, "dashboard/partials/oob_wrap.html", {
                "target_id": "productsTableWrap", "inner_html": table_html,
            })
            action = "ویرایش" if not is_new else "افزوده"
            response["HX-Trigger"] = json.dumps({
                "toast": {"message": f"کالا با موفقیت {action} شد", "type": "ok"},
                "modal-close": {},
            })
            return response
    else:
        initial = None
        if product:
            initial = {
                "name": product.name, "sku": product.sku, "category": product.category_id,
                "brand": product.brand_id,
                "price": product.price, "discount_percent": product.discount_percent,
                "stock": product.stock, "status": product.status, "icon": product.icon,
                "description": product.description, "product_type": product.product_type,
                "barcode": product.barcode, "weight_grams": product.weight_grams,
                "requires_shipping": product.requires_shipping,
                "seo_title": product.seo_title, "seo_description": product.seo_description,
            }
        else:
            initial = {"product_type": Product.ProductType.SIMPLE}
        form = ProductForm(instance=product, initial=initial, store=store)

    return render(request, "dashboard/partials/product_form.html", {"form": form, "product": product})


@require_POST
@staff_required
@permission_required(PRODUCT_DELETE)
def product_delete(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    name = product.name
    product.delete()
    response = render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"کالای «{name}» حذف شد", "type": "info"}})
    return response


# ------------------------------------------------------- تصاویر کالا


@staff_required
@permission_required(MEDIA_MANAGE)
def product_images(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    return render(request, "dashboard/partials/product_images_modal.html", {
        "product": product, "upload_form": ProductImageUploadForm(),
        "variants": product.variants.all(),
    })


def _image_list_response(request, product, *, refresh_table=False):
    list_html = render_to_string(
        "dashboard/partials/product_images_list.html",
        {"product": product, "variants": product.variants.all()},
        request=request,
    )
    if not refresh_table:
        return HttpResponse(list_html)
    table_html = render_to_string(
        "dashboard/partials/products_table_inner.html", _product_list_context(request), request=request,
    )
    oob_html = render_to_string(
        "dashboard/partials/oob_wrap.html", {"target_id": "productsTableWrap", "inner_html": table_html},
    )
    return HttpResponse(list_html + oob_html)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_upload(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    form = ProductImageUploadForm(request.POST, request.FILES)
    errors = []
    added = 0

    if form.is_valid():
        files = form.cleaned_data.get("images") or []
        if not files:
            errors.append("لطفاً حداقل یک تصویر انتخاب کنید.")
        for file in files:
            try:
                add_product_image(product, file)
                added += 1
            except ProductImageError as exc:
                errors.append(f"{file.name}: {exc}")
    else:
        errors.append("فایل انتخاب‌شده معتبر نیست.")

    if not errors:
        toast = {"message": "تصویر با موفقیت اضافه شد", "type": "ok"}
    elif added:
        toast = {"message": f"{added} تصویر اضافه شد؛ {errors[0]}", "type": "info"}
    else:
        toast = {"message": errors[0], "type": "error"}

    response = _image_list_response(request, product, refresh_table=True)
    response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_delete(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    delete_product_image(image)
    response = _image_list_response(request, product, refresh_table=True)
    response["HX-Trigger"] = json.dumps({"toast": {"message": "تصویر حذف شد", "type": "info"}})
    return response


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_set_cover(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    try:
        set_cover_image(product, image_id)
    except ProductImageError:
        pass
    return _image_list_response(request, product, refresh_table=True)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_move(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    direction = request.POST.get("direction", "")
    if direction in ("up", "down"):
        move_product_image(image, direction)
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_alt_update(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    form = ProductImageAltForm(request.POST)
    if form.is_valid():
        update_image_alt(image, form.cleaned_data["alt"])
    return _image_list_response(request, product, refresh_table=False)


@require_POST
@staff_required
@permission_required(MEDIA_MANAGE)
def product_image_variant_update(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    variant_id = request.POST.get("variant", "").strip()
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product) if variant_id else None
    try:
        set_image_variant(image, variant)
    except ProductImageError:
        pass
    return _image_list_response(request, product, refresh_table=False)


# --------------------------------------------------------- تنوع کالا

VARIANTS_PER_PAGE = 25


def _variant_status_filter(request):
    status = request.GET.get("status", "").strip()
    return status if status in ("active", "inactive") else ""


def _variant_search_query(request):
    return request.GET.get("q", "").strip()


def _variant_page_context(request, product, *, bulk_form=None):
    """کانتکست کامل صفحه‌ی مدیریت تنوع: جست‌وجو، فیلتر وضعیت و صفحه‌بندی — همه محدود به همین کالا.

    شمارش‌های خلاصه (کل/فعال/غیرفعال/موجودی) همیشه روی کل تنوع‌های کالا محاسبه می‌شوند،
    نه فقط نتایج جست‌وجو/صفحه‌ی جاری، تا کارت‌های خلاصه گمراه‌کننده نشوند.
    ترتیب جابه‌جایی (بالا/پایین) همیشه روی ترتیب کامل کالا عمل می‌کند، نه ترتیب محلیِ
    نتیجه‌ی فیلترشده یا صفحه‌ی جاری — برای همین وقتی جست‌وجو یا فیلتر فعال است،
    دکمه‌های جابه‌جایی در قالب مخفی می‌شوند (ordering_locked) تا معنای «بالا/پایین»
    هرگز به‌صورت خاموش به ترتیب محلی صفحه تبدیل نشود.
    """
    q = _variant_search_query(request)
    status = _variant_status_filter(request)
    is_filtered = bool(q or status)

    base_qs = product.variants.all()
    variant_count = base_qs.count()
    active_variant_count = base_qs.filter(is_active=True).count()
    inactive_variant_count = variant_count - active_variant_count
    active_variant_stock = base_qs.filter(is_active=True).aggregate(total=Sum("stock"))["total"] or 0

    filtered_qs = base_qs.annotate(
        has_order_history=Exists(OrderItem.objects.filter(variant=OuterRef("pk")))
    )
    if q:
        filtered_qs = filtered_qs.filter(Q(attribute__icontains=q) | Q(value__icontains=q) | Q(sku__icontains=q))
    if status:
        filtered_qs = filtered_qs.filter(is_active=(status == "active"))
    filtered_qs = filtered_qs.order_by("display_order", "attribute", "value").prefetch_related("images")

    paginator = Paginator(filtered_qs, VARIANTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    variants = list(page_obj.object_list)
    prefetch_related_objects([product], "images")
    for variant in variants:
        variant.effective_price = resolve_effective_price(product, variant)
        variant.product = product

    global_ids = list(base_qs.order_by("display_order", "attribute", "value").values_list("pk", flat=True))

    querystring_params = request.GET.copy()
    querystring_params.pop("page", None)

    return {
        "product": product,
        "variants": variants,
        "page_obj": page_obj,
        "variant_count": variant_count,
        "active_variant_count": active_variant_count,
        "inactive_variant_count": inactive_variant_count,
        "active_variant_stock": active_variant_stock,
        "bulk_form": bulk_form or VariantBulkAddForm(),
        "active_page": "products",
        "search_query": q,
        "status_filter": status,
        "is_filtered": is_filtered,
        "ordering_locked": is_filtered,
        "global_first_id": global_ids[0] if global_ids else None,
        "global_last_id": global_ids[-1] if global_ids else None,
        "querystring": querystring_params.urlencode(),
        "full_querystring": request.GET.urlencode(),
    }


def _variant_list_redirect(request, product):
    """بازگشت به صفحه‌ی تنوع‌ها با حفظ جست‌وجو/فیلتر/صفحه‌ی جاری (از querystring همان درخواست)."""
    url = reverse("dashboard:product-variants", args=[product.pk])
    query = request.GET.urlencode()
    return redirect(f"{url}?{query}" if query else url)


def _get_scoped_product(request, pk):
    """کالای همین Store را برمی‌گرداند — نه کالای ساده/متعلق به Store دیگر."""
    return get_object_or_404(Product, pk=pk, store=_resolve_dashboard_store(request))


@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants(request, pk):
    product = _get_scoped_product(request, pk)
    return render(request, "dashboard/product_variants.html", _variant_page_context(request, product))


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_bulk_add(request, pk):
    product = _get_scoped_product(request, pk)
    if not product.is_variable:
        messages.error(request, "برای افزودن تنوع، ابتدا کالا را از ویرایش کالا به «دارای تنوع» تبدیل کنید.")
        return redirect("dashboard:product-variants", pk=product.pk)

    form = VariantBulkAddForm(request.POST)
    if form.is_valid():
        try:
            created, skipped = bulk_create_variants(
                product,
                attribute=form.cleaned_data["attribute"],
                raw_values=form.cleaned_data["raw_values"],
                default_stock=form.cleaned_data["default_stock"],
                default_extra_price=form.cleaned_data["default_extra_price"],
                is_active=form.cleaned_data["is_active"],
            )
        except VariantError as exc:
            form.add_error(None, str(exc))
        else:
            if created:
                message = f"{len(created)} مقدار تنوع اضافه شد"
                if skipped:
                    message += f" — {skipped[0]}"
                messages.success(request, message)
                return redirect("dashboard:product-variants", pk=product.pk)
            form.add_error(None, skipped[0] if skipped else "هیچ مقداری اضافه نشد")

    return render(
        request, "dashboard/product_variants.html", _variant_page_context(request, product, bulk_form=form)
    )


@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_edit(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    if request.method == "POST":
        form = VariantEditForm(request.POST)
        if form.is_valid():
            try:
                update_variant(
                    variant,
                    attribute=form.cleaned_data["attribute"],
                    value=form.cleaned_data["value"],
                    sku=form.cleaned_data["sku"],
                    extra_price=form.cleaned_data["extra_price"],
                    stock=form.cleaned_data["stock"],
                    is_active=form.cleaned_data["is_active"],
                )
            except VariantError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, f"مقدار تنوع «{variant.value}» با موفقیت ویرایش شد")
                back_url = reverse("dashboard:product-variants", args=[product.pk])
                back_query = request.POST.get("back_query", "")
                return redirect(f"{back_url}?{back_query}" if back_query else back_url)
    else:
        form = VariantEditForm(initial={
            "attribute": variant.attribute, "value": variant.value, "sku": variant.sku,
            "extra_price": variant.extra_price, "stock": variant.stock, "is_active": variant.is_active,
        })

    back_url = reverse("dashboard:product-variants", args=[product.pk])
    back_query = request.GET.urlencode() or request.POST.get("back_query", "")
    return render(request, "dashboard/product_variant_edit.html", {
        "product": product, "variant": variant, "form": form, "active_page": "products",
        "back_url": f"{back_url}?{back_query}" if back_query else back_url,
        "back_query": back_query,
    })


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_toggle(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    try:
        if variant.is_active:
            deactivate_variant(variant)
            messages.info(request, f"مقدار تنوع «{variant.value}» غیرفعال شد")
        else:
            update_variant(variant, is_active=True)
            messages.success(request, f"مقدار تنوع «{variant.value}» فعال شد")
    except VariantError as exc:
        messages.error(request, str(exc))

    return _variant_list_redirect(request, product)


@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_delete(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)

    if request.method != "POST":
        if variant.order_items.exists():
            messages.error(
                request,
                f"مقدار تنوع «{variant.value}» در سفارش‌های ثبت‌شده استفاده شده و قابل حذف نیست؛ آن را غیرفعال کنید.",
            )
            return _variant_list_redirect(request, product)
        cancel_url = reverse("dashboard:product-variants", args=[product.pk])
        if request.GET.urlencode():
            cancel_url = f"{cancel_url}?{request.GET.urlencode()}"
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "مقدار تنوع",
            "object_name": f"{variant.attribute}: {variant.value}",
            "cancel_url": cancel_url,
            "active_page": "products",
        })

    try:
        delete_variant(variant)
        messages.success(request, f"مقدار تنوع «{variant.value}» حذف شد")
    except VariantError as exc:
        messages.error(request, str(exc))

    return _variant_list_redirect(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_move(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    direction = request.POST.get("direction", "")

    ordered_ids = list(
        product.variants.order_by("display_order", "attribute", "value").values_list("pk", flat=True)
    )
    if direction in ("up", "down") and variant.pk in ordered_ids:
        index = ordered_ids.index(variant.pk)
        neighbor_index = index - 1 if direction == "up" else index + 1
        if 0 <= neighbor_index < len(ordered_ids):
            ordered_ids[index], ordered_ids[neighbor_index] = ordered_ids[neighbor_index], ordered_ids[index]
            reorder_variants(product, ordered_ids)

    return _variant_list_redirect(request, product)


# --------------------------------------------------------- ویژگی‌ها (Attribute)


ATTRIBUTE_TYPE_FILTERS = [("", "همه‌ی انواع"), *Attribute.DataType.choices]
ATTRIBUTE_STATUS_FILTERS = [("", "همه"), ("active", "فعال"), ("archived", "غیرفعال")]


def _attributes_context(request, *, form=None, value_form=None):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    data_type = request.GET.get("data_type", "")
    status = request.GET.get("status", "")

    qs = Attribute.objects.filter(store=store).select_related("category")
    if q:
        qs = qs.filter(Q(label__icontains=q) | Q(code__icontains=q))
    if data_type in dict(Attribute.DataType.choices):
        qs = qs.filter(data_type=data_type)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "archived":
        qs = qs.filter(is_active=False)

    return {
        "attributes": qs.order_by("display_order", "label"),
        "q": q,
        "selected_data_type": data_type,
        "selected_status": status,
        "type_options": ATTRIBUTE_TYPE_FILTERS,
        "status_options": ATTRIBUTE_STATUS_FILTERS,
        "form": form or AttributeForm(store=store),
        "value_form": value_form or AttributeValueForm(),
        "active_page": "attributes",
    }


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_list(request):
    return render(request, "dashboard/attributes.html", _attributes_context(request))


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_table(request):
    return render(request, "dashboard/partials/attributes_table.html", _attributes_context(request))


def _attributes_table_response(request, *, toast=None):
    response = render(request, "dashboard/partials/attributes_table.html", _attributes_context(request))
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


def _attribute_form_kwargs(form):
    return {
        "label": form.cleaned_data["label"], "code": form.cleaned_data["code"],
        "description": form.cleaned_data["description"],
        "data_type": form.cleaned_data["data_type"], "display_type": form.cleaned_data["display_type"],
        "unit": form.cleaned_data["unit"], "category": form.cleaned_data["category"],
        "is_required": form.cleaned_data["is_required"], "is_filterable": form.cleaned_data["is_filterable"],
        "is_searchable": form.cleaned_data["is_searchable"], "is_comparable": form.cleaned_data["is_comparable"],
        "is_variant_axis": form.cleaned_data["is_variant_axis"],
    }


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_add(request):
    store = _resolve_dashboard_store(request)

    if request.method == "POST":
        form = AttributeForm(request.POST, store=store)
        if form.is_valid():
            try:
                create_attribute(store, **_attribute_form_kwargs(form))
            except AttributeError_ as exc:
                form.add_error(None, str(exc))
            else:
                response = _attributes_table_response(request, toast={"message": "ویژگی اضافه شد", "type": "ok"})
                response["HX-Trigger"] = json.dumps({
                    "toast": {"message": "ویژگی اضافه شد", "type": "ok"}, "modal-close": {},
                })
                return response
    else:
        form = AttributeForm(store=store)

    return render(request, "dashboard/partials/attribute_form_modal.html", {"form": form, "attribute": None})


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_edit(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)

    if request.method == "POST":
        form = AttributeForm(request.POST, store=store)
        if form.is_valid():
            kwargs = _attribute_form_kwargs(form)
            kwargs["code"] = kwargs["code"] or attribute.code
            try:
                update_attribute(attribute, **kwargs)
            except AttributeError_ as exc:
                form.add_error(None, str(exc))
            else:
                response = _attributes_table_response(request, toast={"message": "ویژگی ویرایش شد", "type": "ok"})
                response["HX-Trigger"] = json.dumps({
                    "toast": {"message": "ویژگی ویرایش شد", "type": "ok"}, "modal-close": {},
                })
                return response
    else:
        form = AttributeForm(store=store, initial={
            "label": attribute.label, "code": attribute.code, "description": attribute.description,
            "data_type": attribute.data_type, "display_type": attribute.display_type, "unit": attribute.unit,
            "category": attribute.category_id, "is_required": attribute.is_required,
            "is_filterable": attribute.is_filterable, "is_searchable": attribute.is_searchable,
            "is_comparable": attribute.is_comparable, "is_variant_axis": attribute.is_variant_axis,
        })

    return render(request, "dashboard/partials/attribute_form_modal.html", {"form": form, "attribute": attribute})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_archive(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    archive_attribute(attribute)
    return _attributes_table_response(request, toast={"message": f"«{attribute.label}» غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_activate(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    activate_attribute(attribute)
    return _attributes_table_response(request, toast={"message": f"«{attribute.label}» فعال شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_delete(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    try:
        delete_attribute(attribute)
    except AttributeInUseError as exc:
        return _attributes_table_response(request, toast={"message": str(exc), "type": "err"})
    return _attributes_table_response(request, toast={"message": "ویژگی حذف شد", "type": "info"})


@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_values(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    return render(request, "dashboard/partials/attribute_values_modal.html", {
        "attribute": attribute, "value_form": AttributeValueForm(),
    })


def _attribute_values_response(request, attribute, *, toast=None):
    response = render(request, "dashboard/partials/attribute_values_list.html", {
        "attribute": attribute, "value_form": AttributeValueForm(),
    })
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_add(request, pk):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    form = AttributeValueForm(request.POST)
    if form.is_valid():
        try:
            create_attribute_value(
                attribute, label=form.cleaned_data["label"], value=form.cleaned_data["value"],
                color_hex=form.cleaned_data["color_hex"],
            )
        except AttributeError_ as exc:
            return render(request, "dashboard/partials/attribute_values_list.html", {
                "attribute": attribute, "value_form": form, "form_error": str(exc),
            })
        return _attribute_values_response(request, attribute, toast={"message": "مقدار اضافه شد", "type": "ok"})
    return render(request, "dashboard/partials/attribute_values_list.html", {
        "attribute": attribute, "value_form": form,
    })


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_archive(request, pk, value_id):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    value = get_object_or_404(AttributeValue, pk=value_id, attribute=attribute)
    archive_attribute_value(value)
    return _attribute_values_response(request, attribute, toast={"message": "مقدار غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(ATTRIBUTE_MANAGE)
def attribute_value_delete(request, pk, value_id):
    store = _resolve_dashboard_store(request)
    attribute = get_object_or_404(Attribute, pk=pk, store=store)
    value = get_object_or_404(AttributeValue, pk=value_id, attribute=attribute)
    try:
        delete_attribute_value(value)
    except AttributeInUseError as exc:
        return _attribute_values_response(request, attribute, toast={"message": str(exc), "type": "err"})
    return _attribute_values_response(request, attribute, toast={"message": "مقدار حذف شد", "type": "info"})


# ------------------------------------------- محور/مقدار تنوع چندمحوره (Variant Engine)


def _product_options_context(request, product):
    axes = list(
        product.options.all().order_by("position").prefetch_related("values")
    )
    variants = list(
        product.variants.exclude(combination_key="").order_by("display_order")
        .prefetch_related("option_values__option", "option_values__option_value")
    )
    return {
        "product": product,
        "axes": axes,
        "variants": variants,
        "obsolete_variants": [v for v in variants if v.is_obsolete],
        "active_variants": [v for v in variants if not v.is_obsolete],
        "combination_preview": preview_combination_count(product),
        "has_legacy_variants": product.variants.filter(combination_key="").exists(),
        "option_form": ProductOptionForm(),
        "option_value_form": ProductOptionValueAddForm(),
        "active_page": "products",
    }


def _product_options_response(request, product, *, toast=None):
    response = render(
        request, "dashboard/partials/product_options_body.html", _product_options_context(request, product),
    )
    if toast:
        response["HX-Trigger"] = json.dumps({"toast": toast})
    return response


@staff_required
@permission_required(VARIANT_MANAGE)
def product_options(request, pk):
    product = _get_scoped_product(request, pk)
    return render(request, "dashboard/product_options.html", _product_options_context(request, product))


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_add(request, pk):
    product = _get_scoped_product(request, pk)
    form = ProductOptionForm(request.POST)
    if form.is_valid():
        raw_values = form.cleaned_data["raw_values"]
        values = parse_bulk_values(raw_values) if raw_values else []
        try:
            add_product_option(product, label=form.cleaned_data["label"], values=values)
        except VariantEngineError as exc:
            return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
        return _product_options_response(request, product, toast={"message": "محور تنوع اضافه شد", "type": "ok"})
    return _product_options_response(request, product, toast={"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_deactivate(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    deactivate_product_option(option)
    return _product_options_response(request, product, toast={
        "message": f"محور «{option.label}» غیرفعال شد — برای اعمال، دوباره تولید کنید.", "type": "info",
    })


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_activate(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    activate_product_option(option)
    return _product_options_response(request, product, toast={"message": f"محور «{option.label}» فعال شد", "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_options_reorder(request, pk):
    product = _get_scoped_product(request, pk)
    ordered_ids = [int(v) for v in request.POST.getlist("option_ids") if v.isdigit()]
    reorder_product_options(product, ordered_ids)
    return _product_options_response(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_move(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    direction = request.POST.get("direction", "")

    ordered_ids = list(product.options.order_by("position").values_list("pk", flat=True))
    if direction in ("up", "down") and option.pk in ordered_ids:
        index = ordered_ids.index(option.pk)
        neighbor_index = index - 1 if direction == "up" else index + 1
        if 0 <= neighbor_index < len(ordered_ids):
            ordered_ids[index], ordered_ids[neighbor_index] = ordered_ids[neighbor_index], ordered_ids[index]
            reorder_product_options(product, ordered_ids)

    return _product_options_response(request, product)


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_value_add(request, pk, option_id):
    product = _get_scoped_product(request, pk)
    option = get_object_or_404(ProductOption, pk=option_id, product=product)
    form = ProductOptionValueAddForm(request.POST)
    if form.is_valid():
        try:
            add_option_value(option, form.cleaned_data["label"], color_hex=form.cleaned_data["color_hex"])
        except VariantEngineError as exc:
            return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
        return _product_options_response(request, product, toast={"message": "مقدار اضافه شد", "type": "ok"})
    return _product_options_response(request, product, toast={"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_option_value_remove(request, pk, value_id):
    product = _get_scoped_product(request, pk)
    value = get_object_or_404(ProductOptionValue, pk=value_id, option__product=product)
    label = value.label
    remove_option_value(value)
    return _product_options_response(request, product, toast={"message": f"مقدار «{label}» حذف/غیرفعال شد", "type": "info"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_generate(request, pk):
    product = _get_scoped_product(request, pk)
    try:
        result = generate_variants(product)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})

    parts = []
    if result.created:
        parts.append(f"{len(result.created)} تنوع جدید ساخته شد")
    if result.obsoleted:
        parts.append(f"{len(result.obsoleted)} ترکیب منسوخ شد")
    if not parts:
        parts.append("همه‌ی ترکیب‌ها از قبل موجود بودند")
    message = "، ".join(parts) + f" — {len(result.preserved) + len(result.created)} تنوع فعال"
    return _product_options_response(request, product, toast={"message": message, "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variant_set_default(request, pk, variant_id):
    product = _get_scoped_product(request, pk)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product)
    try:
        set_default_variant(product, variant)
    except VariantEngineError as exc:
        return _product_options_response(request, product, toast={"message": str(exc), "type": "err"})
    return _product_options_response(request, product, toast={"message": "تنوع پیش‌فرض تغییر کرد", "type": "ok"})


@require_POST
@staff_required
@permission_required(VARIANT_MANAGE)
def product_variants_bulk_update(request, pk):
    product = _get_scoped_product(request, pk)
    variant_ids = [int(v) for v in request.POST.getlist("variant_ids") if v.isdigit()]
    variants = {v.pk: v for v in product.variants.filter(pk__in=variant_ids)}

    updated = []
    errors = []
    for variant_id in variant_ids:
        variant = variants.get(variant_id)
        if variant is None:
            continue
        prefix = f"variant_{variant_id}_"
        try:
            sku = request.POST.get(f"{prefix}sku", "").strip()
            if sku and sku != variant.sku:
                if ProductVariant.objects.filter(store=product.store, sku=sku).exclude(pk=variant.pk).exists():
                    raise VariantError(f"کد کالای «{sku}» قبلاً برای یک تنوع دیگر استفاده شده است.")
                variant.sku = sku
            variant.barcode = request.POST.get(f"{prefix}barcode", "").strip()
            variant.stock = int(normalize_digits(request.POST.get(f"{prefix}stock", "0")) or 0)
            variant.extra_price = Decimal(normalize_digits(request.POST.get(f"{prefix}extra_price", "0")) or 0)
            compare_at_raw = normalize_digits(request.POST.get(f"{prefix}compare_at_price", "")).strip()
            variant.compare_at_price = Decimal(compare_at_raw) if compare_at_raw else None
            cost_raw = normalize_digits(request.POST.get(f"{prefix}cost", "")).strip()
            variant.cost = Decimal(cost_raw) if cost_raw else None
            variant.is_active = request.POST.get(f"{prefix}is_active") == "on"
            if variant.stock < 0:
                raise VariantError("موجودی نمی‌تواند منفی باشد.")
            variant.full_clean(exclude=["normalized_attribute", "normalized_value"])
        except (VariantError, ValidationError, InvalidOperation, ValueError) as exc:
            message = "؛ ".join(sum(exc.message_dict.values(), [])) if isinstance(exc, ValidationError) else str(exc)
            errors.append(f"{variant.value}: {message}")
            continue
        updated.append(variant)

    if errors:
        return _product_options_response(request, product, toast={"message": errors[0], "type": "err"})

    for variant in updated:
        variant.save()

    return _product_options_response(
        request, product, toast={"message": f"{len(updated)} تنوع به‌روزرسانی شد", "type": "ok"},
    )


# --------------------------------------------------------- دسته‌بندی‌ها


def _categories_context(request, *, main_form=None, sub_form=None):
    store = _resolve_dashboard_store(request)
    context = category_tree_context(store)
    context["main_form"] = main_form or MainCategoryForm()
    context["sub_form"] = sub_form or SubCategoryForm(store=store)
    return context


@staff_required
@permission_required(CATEGORY_MANAGE)
def category_list(request):
    context = _categories_context(request)
    context["active_page"] = "categories"
    return render(request, "dashboard/categories.html", context)


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_add_main(request):
    store = _resolve_dashboard_store(request)
    form = MainCategoryForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            store=store, name=name, icon=form.cleaned_data["icon"] or "📁",
            slug=generate_unique_slug(Category, name, store=store),
        )
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": f"گروه «{name}» اضافه شد", "type": "ok"}})
        return response
    response = render(
        request, "dashboard/partials/categories_body.html", _categories_context(request, main_form=form)
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_add_sub(request):
    store = _resolve_dashboard_store(request)
    form = SubCategoryForm(request.POST, store=store)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            store=store, name=name, icon=form.cleaned_data["icon"], parent=form.cleaned_data["parent"],
            slug=generate_unique_slug(Category, name, store=store),
        )
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": f"زیرگروه «{name}» اضافه شد", "type": "ok"}})
        return response
    response = render(
        request, "dashboard/partials/categories_body.html", _categories_context(request, sub_form=form)
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": "لطفاً خطاهای فرم را برطرف کنید", "type": "err"}})
    return response


@staff_required
@permission_required(CATEGORY_MANAGE)
def category_edit(request, pk):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)

    if request.method == "POST":
        form = CategoryEditForm(request.POST)
        if form.is_valid():
            category.name = form.cleaned_data["name"]
            category.icon = form.cleaned_data["icon"]
            category.save(update_fields=["name", "icon", "updated_at"])
            context = _categories_context(request)
            context["oob"] = True
            response = render(request, "dashboard/partials/categories_body.html", context)
            response["HX-Trigger"] = json.dumps({
                "toast": {"message": "دسته‌بندی ویرایش شد", "type": "ok"}, "modal-close": {},
            })
            return response
    else:
        form = CategoryEditForm(initial={"name": category.name, "icon": category.icon})

    return render(request, "dashboard/partials/category_edit_form.html", {"form": form, "category": category})


@require_POST
@staff_required
@permission_required(CATEGORY_MANAGE)
def category_delete(request, pk):
    store = _resolve_dashboard_store(request)
    category = get_object_or_404(Category, pk=pk, store=store)
    try:
        can_delete_category(category)
    except CategoryDeleteError as exc:
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({"toast": {"message": str(exc), "type": "err"}})
        return response

    name = category.name
    try:
        category.delete()
    except ProtectedError:
        response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
        response["HX-Trigger"] = json.dumps({
            "toast": {"message": f"دسته‌ی «{name}» دارای کالا است و قابل حذف نیست.", "type": "err"},
        })
        return response
    response = render(request, "dashboard/partials/categories_body.html", _categories_context(request))
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"«{name}» حذف شد", "type": "info"}})
    return response


# --------------------------------------------------------------- سفارش‌ها


def _order_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    return {
        "orders": filtered_orders(store=store, q=q, status=status),
        "q": q,
        "selected_status": status,
        "status_filters": ORDER_STATUS_FILTERS,
        "status_counts": order_status_counts(store=store),
    }


@staff_required
@permission_required(ORDER_VIEW)
def order_list(request):
    context = _order_list_context(request)
    context["active_page"] = "orders"
    return render(request, "dashboard/orders.html", context)


@staff_required
@permission_required(ORDER_VIEW)
def order_table(request):
    return render(request, "dashboard/partials/orders_table_inner.html", _order_list_context(request))


@staff_required
@permission_required(ORDER_VIEW)
def order_detail(request, code):
    store = _resolve_dashboard_store(request)
    order = get_object_or_404(
        Order.objects.select_related("customer", "vendor", "shipping_method"), code=code, store=store
    )

    if request.method == "POST":
        if not membership_has_permission(request.store_membership, ORDER_STATUS_CHANGE):
            return render(request, "dashboard/403.html", status=403)
        to_status = request.POST.get("status", "")
        tracking_code = request.POST.get("tracking_code", "").strip()
        try:
            change_order_status(
                order, to_status, by=request.user, tracking_code=tracking_code, store=store,
            )
            messages.success(request, f"وضعیت سفارش {order.code} به‌روزرسانی شد")
            return redirect("dashboard:order-detail", code=order.code)
        except ValueError as exc:
            context = _order_detail_context(order)
            context["active_page"] = "orders"
            context["error"] = str(exc)
            return render(request, "dashboard/order_detail.html", context)

    context = _order_detail_context(order)
    context["active_page"] = "orders"
    return render(request, "dashboard/order_detail.html", context)


def _order_detail_context(order):
    return {
        "order": order,
        "items": order.items.select_related("product", "variant"),
        "status_history": order.status_history.select_related("changed_by"),
        "next_status_options": next_status_options(order),
        "is_final": order_is_final(order),
        "status_steps": order_status_steps(order),
    }


# ---------------------------------------------------------------- فاکتورها


def _invoice_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    orders_qs = filtered_invoices(store=store, q=q, status=status)
    count, total = invoice_totals(orders_qs)
    return {
        "orders": orders_qs,
        "q": q,
        "selected_status": status,
        "status_filters": INVOICE_STATUS_FILTERS,
        "invoice_count": count,
        "invoice_total": total,
    }


@staff_required
@permission_required(ORDER_VIEW)
def invoice_list(request):
    context = _invoice_list_context(request)
    context["active_page"] = "invoices"
    return render(request, "dashboard/invoices.html", context)


@staff_required
@permission_required(ORDER_VIEW)
def invoice_table(request):
    return render(request, "dashboard/partials/invoices_table_inner.html", _invoice_list_context(request))


@staff_required
@permission_required(ORDER_VIEW)
def invoice_detail(request, code):
    store = _resolve_dashboard_store(request)
    order = get_object_or_404(Order.objects.select_related("customer"), code=code, store=store)
    context = {
        "order": order,
        "items": order.items.select_related("product"),
        "active_page": "invoices",
    }
    return render(request, "dashboard/invoice_detail.html", context)


# ---------------------------------------------------------------- پرداخت‌ها


def _payment_list_context(request):
    store = _resolve_dashboard_store(request)
    status = request.GET.get("status", "")
    return {
        "transactions": filtered_transactions(store=store, status=status),
        "selected_status": status,
        "status_filters": TRANSACTION_STATUS_FILTERS,
    }


@staff_required
@permission_required(ORDER_VIEW)
def payment_list(request):
    context = _payment_list_context(request)
    context["active_page"] = "payments"
    return render(request, "dashboard/payments.html", context)


@staff_required
@permission_required(ORDER_VIEW)
def payment_table(request):
    return render(request, "dashboard/partials/payments_table_inner.html", _payment_list_context(request))


# ---------------------------------------------------------------- مشتریان


def _customer_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    return {"customers": customers_admin_service.annotated_customers(store=store, q=q), "q": q}


@staff_required
@permission_required(CUSTOMER_VIEW)
def customer_list(request):
    context = _customer_list_context(request)
    context["active_page"] = "customers"
    return render(request, "dashboard/customers.html", context)


@staff_required
@permission_required(CUSTOMER_VIEW)
def customer_table(request):
    return render(request, "dashboard/partials/customers_table_inner.html", _customer_list_context(request))


@staff_required
@permission_required(CUSTOMER_VIEW)
def customer_detail(request, pk):
    """مشتری فقط اگر حداقل یک Order در همین Store داشته باشد قابل‌دسترسی
    است — Customer فیلد store ندارد (تصمیم عمدی، نگاه کنید به
    customers_admin_service)، پس مرز دسترسی از طریق رابطه‌ی Order اعمال
    می‌شود، نه یک فیلد مستقیم روی Customer."""
    store = _resolve_dashboard_store(request)
    customer = get_object_or_404(Customer.objects.filter(orders__store=store).distinct(), pk=pk)
    orders = customers_admin_service.customer_orders(customer, store=store)
    context = {
        "customer": customer,
        "orders": orders,
        "paid_total": customers_admin_service.customer_paid_total(orders),
        "active_page": "customers",
    }
    return render(request, "dashboard/customer_detail.html", context)


# -------------------------------------------------------- گزارش‌های حرفه‌ای


@staff_required
@permission_required(REPORTS_VIEW)
def report_list(request):
    store = _resolve_dashboard_store(request)
    context = report_service.build_report_context(store, request.GET.get("range", "30"))
    context["active_page"] = "reports"
    return render(request, "dashboard/reports.html", context)


@staff_required
@permission_required(REPORTS_VIEW)
def report_partial(request):
    store = _resolve_dashboard_store(request)
    context = report_service.build_report_context(store, request.GET.get("range", "30"))
    return render(request, "dashboard/partials/reports_body.html", context)


# ------------------------------------------------------------------ تنظیمات


THEME_TOKEN_DEFAULTS = {
    "primary_color": "#6D28D9", "accent_color": "#FF4D77", "secondary_color": "#7C3AED",
    "background_color": "#F7F5FC", "surface_color": "#FFFFFF", "text_color": "#241C3A",
    "muted_text_color": "#8B86A3",
}


def _settings_context(request, *, shop_form=None, finance_form=None, sms_form=None, visual_form=None):
    store = _resolve_dashboard_store(request)
    shop = ShopSettings.load(store=store)
    theme_values = {
        field: safe_hex(getattr(shop, field), default) for field, default in THEME_TOKEN_DEFAULTS.items()
    }
    return {
        "shop": shop,
        "shop_form": shop_form or ShopInfoForm(initial={
            "name": shop.name, "tagline": shop.tagline, "contact_phone": shop.contact_phone,
            "contact_email": shop.contact_email, "contact_address": shop.contact_address,
            "description": shop.description,
        }),
        "finance_form": finance_form or FinanceSettingsForm(initial={
            "tax_percent": shop.tax_percent, "free_shipping_threshold": shop.free_shipping_threshold,
        }),
        "sms_form": sms_form or SmsConnectionForm(initial={
            "sms_enabled": shop.sms_enabled, "sms_backend": shop.sms_backend,
            "sms_sender_number": shop.sms_sender_number,
            "melipayamak_username": shop.melipayamak_username,
            "melipayamak_password": shop.melipayamak_password,
        }),
        "visual_form": visual_form or VisualIdentityForm(current_shop=shop, initial=theme_values),
        "theme_presets": THEME_PRESETS,
        "selected_preset_key": matching_preset_key(
            primary=theme_values["primary_color"], secondary=theme_values["secondary_color"],
            accent=theme_values["accent_color"], background=theme_values["background_color"],
        ),
        "sms_template_rows": sms_admin_service.templates_with_variables(),
        "sms_test_form": SmsTestForm(),
        "gateways": settings_admin_service.active_gateways_context(store=store),
        "shipping_methods": settings_admin_service.shipping_methods_context(store=store),
        "gateway_configs": settings_admin_service.gateway_configs_context(store=store),
        "active_page": "settings",
    }


SETTINGS_SECTIONS = [
    ("general", "اطلاعات فروشگاه", "🏪", "نام، شعار و اطلاعات تماس فروشگاه"),
    ("finance", "مالی و مالیات", "💰", "نرخ مالیات و آستانه‌ی ارسال رایگان"),
    ("delivery-payment", "ارسال و درگاه", "🚚", "روش‌های ارسال و درگاه‌های پرداخت"),
    ("payment-config", "پیکربندی درگاه", "🔐", "تنظیمات اعتبارنامه و فعال‌سازی درگاه‌های پرداخت"),
    ("sms", "پیامک", "📲", "اتصال و قالب‌های پیامک"),
    ("appearance", "تم رنگی", "🎨", "پیش‌فرض‌ها و رنگ‌بندی سفارشی فروشگاه"),
]

VALID_SECTION_KEYS = {s[0] for s in SETTINGS_SECTIONS}


@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_home(request):
    section = request.GET.get("section", "general")
    if section not in VALID_SECTION_KEYS:
        section = "general"
    context = _settings_context(request)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = section
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_shop_info(request):
    form = ShopInfoForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        for field in ["name", "tagline", "contact_phone", "contact_email", "contact_address", "description"]:
            setattr(shop, field, form.cleaned_data[field])
        shop.save()
        messages.success(request, "اطلاعات فروشگاه ذخیره شد")
        return redirect("/admin-portal/settings/?section=general")
    context = _settings_context(request, shop_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "general"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_finance(request):
    form = FinanceSettingsForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        shop.tax_percent = form.cleaned_data["tax_percent"]
        shop.free_shipping_threshold = form.cleaned_data["free_shipping_threshold"]
        shop.save()
        messages.success(request, "تنظیمات مالی ذخیره شد")
        return redirect("/admin-portal/settings/?section=finance")
    context = _settings_context(request, finance_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "finance"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_gateway_toggle(request, pk):
    gateway = settings_admin_service.toggle_gateway(pk, store=_resolve_dashboard_store(request))
    state = "فعال" if gateway.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"درگاه «{gateway.name}» {state} شد", "type": "info"}})
    return response


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_shipping_toggle(request, pk):
    method = settings_admin_service.toggle_shipping_method(pk, store=_resolve_dashboard_store(request))
    state = "فعال" if method.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": f"روش ارسال «{method.name}» {state} شد", "type": "info"},
    })
    return response


# --------------------------------------------------------------- هویت بصری


@require_POST
@staff_required
@permission_required(SETTINGS_MANAGE)
def settings_appearance(request):
    """ذخیره تنظیمات هویت بصری: لوگو، فاوآیکون، توکن‌های رنگی تم؛ یا بازگردانی به پیش‌فرض."""
    from django.db import transaction as db_transaction

    if request.POST.get("action") == "reset":
        shop = ShopSettings.load(store=request.store)
        for field, default in THEME_TOKEN_DEFAULTS.items():
            setattr(shop, field, default)
        shop.save()
        messages.success(request, "رنگ‌بندی به پیش‌فرض بازگردانی شد")
        return redirect("/admin-portal/settings/?section=appearance")

    shop_for_validation = ShopSettings.load(store=request.store)
    form = VisualIdentityForm(request.POST, request.FILES, current_shop=shop_for_validation)
    if form.is_valid():
        shop = shop_for_validation
        old_logo_name = shop.logo.name if shop.logo else None
        old_favicon_name = shop.favicon.name if shop.favicon else None

        # رنگ‌ها — primary/accent همیشه اجباری‌اند؛ توکن‌های جدید فقط اگر ارسال شده باشند بازنویسی می‌شوند
        shop.primary_color = form.cleaned_data["primary_color"]
        shop.accent_color = form.cleaned_data["accent_color"]
        for field in ("secondary_color", "background_color", "surface_color", "text_color", "muted_text_color"):
            if form.cleaned_data.get(field):
                setattr(shop, field, form.cleaned_data[field])

        # لوگو — replacement wins over removal
        if form.cleaned_data.get("logo"):
            shop.logo = form.cleaned_data["logo"]
        elif form.cleaned_data.get("remove_logo") and shop.logo:
            shop.logo = ""

        # فاوآیکون — replacement wins over removal
        if form.cleaned_data.get("favicon"):
            shop.favicon = form.cleaned_data["favicon"]
        elif form.cleaned_data.get("remove_favicon") and shop.favicon:
            shop.favicon = ""

        shop.save()

        # پاکسازی فایل‌های قبلی فقط پس از ذخیره‌ی موفق (Storage-safe)
        if old_logo_name and old_logo_name != (shop.logo.name if shop.logo else ""):
            storage = shop.logo.storage
            db_transaction.on_commit(lambda n=old_logo_name, s=storage: (
                s.delete(n) if s.exists(n) else None
            ))
        if old_favicon_name and old_favicon_name != (shop.favicon.name if shop.favicon else ""):
            storage = shop.favicon.storage
            db_transaction.on_commit(lambda n=old_favicon_name, s=storage: (
                s.delete(n) if s.exists(n) else None
            ))

        messages.success(request, "هویت بصری فروشگاه ذخیره شد")
        return redirect("/admin-portal/settings/?section=appearance")

    context = _settings_context(request, visual_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "appearance"
    return render(request, "dashboard/settings.html", context)


# --------------------------------------------------------------- پیامک


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def settings_sms_connection(request):
    form = SmsConnectionForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        for field in [
            "sms_enabled", "sms_backend", "sms_sender_number",
            "melipayamak_username", "melipayamak_password",
        ]:
            setattr(shop, field, form.cleaned_data[field])
        shop.save()
        messages.success(request, "تنظیمات اتصال پیامک ذخیره شد")
        return redirect("/admin-portal/settings/?section=sms")
    context = _settings_context(request, sms_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "sms"
    return render(request, "dashboard/settings.html", context)


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_template_form(request, pk):
    template = get_object_or_404(SmsTemplate, pk=pk)

    if request.method == "POST":
        form = SmsTemplateForm(request.POST, event_key=template.event_key)
        if form.is_valid():
            template.body = form.cleaned_data["body"]
            template.save(update_fields=["body", "updated_at"])
            table_html = render_to_string(
                "dashboard/partials/sms_templates_table.html",
                {"sms_template_rows": sms_admin_service.templates_with_variables()},
                request=request,
            )
            response = render(request, "dashboard/partials/oob_wrap.html", {
                "target_id": "smsTemplatesWrap", "inner_html": table_html,
            })
            response["HX-Trigger"] = json.dumps({
                "toast": {"message": "قالب پیامک ذخیره شد", "type": "ok"},
                "modal-close": {},
            })
            return response
    else:
        form = SmsTemplateForm(event_key=template.event_key, initial={"body": template.body})

    variables = EVENT_VARIABLES.get(template.event_key, {})
    return render(
        request, "dashboard/partials/sms_template_form.html",
        {"form": form, "template": template, "variables": variables},
    )


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_template_toggle(request, pk):
    template = get_object_or_404(SmsTemplate, pk=pk)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if template.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": f"پیامک «{template.title}» {state} شد", "type": "info"},
    })
    return response


@require_POST
@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_test_send(request):
    form = SmsTestForm(request.POST)
    event_key = request.POST.get("event_key", "")
    if form.is_valid():
        try:
            log = send_test_sms(
                event_key=event_key, phone=form.cleaned_data["phone"],
                store=_resolve_dashboard_store(request),
            )
        except SmsTemplateError as exc:
            messages.error(request, str(exc))
        else:
            if log.status == log.Status.SENT:
                messages.success(request, f"پیامک آزمایشی ارسال شد (وضعیت: {log.get_status_display()})")
            else:
                messages.error(request, f"ارسال ناموفق بود: {log.error_message or 'خطای نامشخص'}")
    else:
        messages.error(request, "شماره موبایل معتبر نیست")
    return redirect("/admin-portal/settings/?section=sms")


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_log_list(request):
    context = {
        "logs": sms_admin_service.filtered_logs(status=request.GET.get("status", "")),
        "selected_status": request.GET.get("status", ""),
        "status_filters": sms_admin_service.LOG_STATUS_FILTERS,
        "active_page": "settings",
    }
    return render(request, "dashboard/sms_logs.html", context)


@staff_required
@permission_required(SMS_SETTINGS_MANAGE)
def sms_log_table(request):
    context = {
        "logs": sms_admin_service.filtered_logs(status=request.GET.get("status", "")),
        "selected_status": request.GET.get("status", ""),
        "status_filters": sms_admin_service.LOG_STATUS_FILTERS,
    }
    return render(request, "dashboard/partials/sms_logs_table_inner.html", context)



# ---------------------------------------------------------------- صفحات محتوایی

from apps.content.models import ContentPage


@staff_required
@permission_required(CONTENT_MANAGE)
def page_list(request):
    pages = ContentPage.objects.all().order_by("-created_at")
    context = {"pages": pages, "active_page": "pages"}
    return render(request, "dashboard/pages.html", context)


@staff_required
@permission_required(CONTENT_MANAGE)
def page_form(request, pk=None):
    from django.utils.text import slugify as django_slugify

    page = get_object_or_404(ContentPage, pk=pk) if pk else None

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        slug = request.POST.get("slug", "").strip()
        body = request.POST.get("body", "")
        summary = request.POST.get("summary", "").strip()
        seo_title = request.POST.get("seo_title", "").strip()
        seo_description = request.POST.get("seo_description", "").strip()
        show_in_footer = request.POST.get("show_in_footer") == "on"
        footer_column = request.POST.get("footer_column", "")
        display_order = int(request.POST.get("display_order", "0") or "0")

        if not title:
            messages.error(request, "عنوان صفحه الزامی است")
            return redirect(request.path)

        if not slug:
            slug = django_slugify(title, allow_unicode=True) or "page"

        if page is None:
            page = ContentPage()

        page.title = title
        page.slug = slug
        page.body = body
        page.summary = summary
        page.seo_title = seo_title
        page.seo_description = seo_description
        page.show_in_footer = show_in_footer
        page.footer_column = footer_column
        page.display_order = display_order

        try:
            page.full_clean()
            page.save()
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"صفحه‌ی «{page.title}» با موفقیت {action} شد")
            return redirect("dashboard:page-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                msg = " ".join(v[0] if isinstance(v, list) else v for v in exc.message_dict.values())
            else:
                msg = str(exc)
            messages.error(request, msg)
            return redirect(request.path)

    context = {"page": page, "active_page": "pages", "footer_columns": ContentPage.FooterColumn.choices}
    return render(request, "dashboard/page_form.html", context)


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def page_delete(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    title = page.title
    page.delete()
    messages.success(request, f"صفحه‌ی «{title}» حذف شد")
    return redirect("dashboard:page-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def page_publish(request, pk):
    from django.utils import timezone

    page = get_object_or_404(ContentPage, pk=pk)
    if page.status == ContentPage.Status.PUBLISHED:
        page.status = ContentPage.Status.DRAFT
        page.published_at = None
        page.published_by = None
        messages.info(request, f"صفحه‌ی «{page.title}» به پیش‌نویس برگشت")
    else:
        page.status = ContentPage.Status.PUBLISHED
        page.published_at = timezone.now()
        page.published_by = request.user
        messages.success(request, f"صفحه‌ی «{page.title}» منتشر شد")
    page.save()
    return redirect("dashboard:page-list")



# ---------------------------------------------------------------- صفحه اصلی (اسلاید و بنر)

from apps.content.models import HeroSlide, PromotionalBanner


@staff_required
@permission_required(CONTENT_MANAGE)
def hero_list(request):
    slides = HeroSlide.objects.all().order_by("display_order", "id")
    return render(request, "dashboard/hero_list.html", {"slides": slides, "active_page": "homepage"})


@staff_required
@permission_required(CONTENT_MANAGE)
def hero_form(request, pk=None):
    from django.db import transaction

    from apps.catalog.models import Brand, Category
    slide = get_object_or_404(HeroSlide, pk=pk) if pk else None

    if request.method == "POST":
        obj = slide or HeroSlide()

        # Capture old file names before modification
        old_desktop_name = obj.desktop_image.name if obj.pk and obj.desktop_image else None
        old_mobile_name = obj.mobile_image.name if obj.pk and obj.mobile_image else None

        obj.title = request.POST.get("title", "").strip()
        obj.subtitle = request.POST.get("subtitle", "").strip()
        obj.button_label = request.POST.get("button_label", "").strip()
        obj.show_button = request.POST.get("show_button") == "on"
        obj.is_active = request.POST.get("is_active") == "on"
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.destination_type = request.POST.get("destination_type", "none")
        obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
        obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"

        # FK destinations
        cat_id = request.POST.get("destination_category") or None
        prod_id = request.POST.get("destination_product") or None
        brand_id = request.POST.get("destination_brand") or None
        obj.destination_category_id = int(cat_id) if cat_id else None
        obj.destination_product_id = int(prod_id) if prod_id else None
        obj.destination_brand_id = int(brand_id) if brand_id else None

        # Images
        if "desktop_image" in request.FILES:
            obj.desktop_image = request.FILES["desktop_image"]
        if "mobile_image" in request.FILES:
            obj.mobile_image = request.FILES["mobile_image"]
        if request.POST.get("remove_mobile") == "on" and "mobile_image" not in request.FILES:
            obj.mobile_image = ""

        try:
            obj.full_clean()
            obj.save()

            # Schedule old file cleanup after successful commit
            storage = HeroSlide.desktop_image.field.storage
            new_desktop_name = obj.desktop_image.name if obj.desktop_image else None
            new_mobile_name = obj.mobile_image.name if obj.mobile_image else None

            files_to_delete = []
            if old_desktop_name and old_desktop_name != new_desktop_name:
                files_to_delete.append(old_desktop_name)
            if old_mobile_name and old_mobile_name != new_mobile_name:
                files_to_delete.append(old_mobile_name)

            if files_to_delete:
                transaction.on_commit(lambda: [
                    storage.delete(f) for f in files_to_delete if storage.exists(f)
                ])

            messages.success(request, f"اسلاید «{obj.title or obj.pk}» ذخیره شد")
            return redirect("dashboard:hero-list")
        except (ValidationError, IntegrityError) as exc:
            msg = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, msg)

    categories = Category.objects.filter(is_active=True).order_by("order", "name")
    return render(request, "dashboard/hero_form.html", {
        "slide": slide, "active_page": "homepage", "categories": categories,
    })


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def hero_delete(request, pk):
    from django.db import transaction

    slide = get_object_or_404(HeroSlide, pk=pk)
    desktop_name = slide.desktop_image.name if slide.desktop_image else None
    mobile_name = slide.mobile_image.name if slide.mobile_image else None
    storage = slide.desktop_image.storage

    slide.delete()

    # Delete owned files only after successful DB commit
    def _cleanup():
        if desktop_name and storage.exists(desktop_name):
            storage.delete(desktop_name)
        if mobile_name and storage.exists(mobile_name):
            storage.delete(mobile_name)

    transaction.on_commit(_cleanup)
    messages.success(request, "اسلاید حذف شد")
    return redirect("dashboard:hero-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def hero_toggle(request, pk):
    slide = get_object_or_404(HeroSlide, pk=pk)
    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if slide.is_active else "غیرفعال"
    messages.info(request, f"اسلاید {state} شد")
    return redirect("dashboard:hero-list")


@staff_required
@permission_required(CONTENT_MANAGE)
def banner_list(request):
    banners = PromotionalBanner.objects.all().order_by("display_order", "id")
    return render(request, "dashboard/banner_list.html", {"banners": banners, "active_page": "homepage"})


@staff_required
@permission_required(CONTENT_MANAGE)
def banner_form(request, pk=None):
    from django.db import transaction

    from apps.catalog.models import Brand, Category
    banner = get_object_or_404(PromotionalBanner, pk=pk) if pk else None

    if request.method == "POST":
        obj = banner or PromotionalBanner()

        # Capture old file names before modification
        old_desktop_name = obj.desktop_image.name if obj.pk and obj.desktop_image else None
        old_mobile_name = obj.mobile_image.name if obj.pk and obj.mobile_image else None

        obj.title = request.POST.get("title", "").strip()
        obj.description = request.POST.get("description", "").strip()
        obj.button_label = request.POST.get("button_label", "").strip()
        obj.show_button = request.POST.get("show_button") == "on"
        obj.is_active = request.POST.get("is_active") == "on"
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.destination_type = request.POST.get("destination_type", "none")
        obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
        obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"

        cat_id = request.POST.get("destination_category") or None
        prod_id = request.POST.get("destination_product") or None
        brand_id = request.POST.get("destination_brand") or None
        obj.destination_category_id = int(cat_id) if cat_id else None
        obj.destination_product_id = int(prod_id) if prod_id else None
        obj.destination_brand_id = int(brand_id) if brand_id else None

        if "desktop_image" in request.FILES:
            obj.desktop_image = request.FILES["desktop_image"]
        if "mobile_image" in request.FILES:
            obj.mobile_image = request.FILES["mobile_image"]
        if request.POST.get("remove_mobile") == "on" and "mobile_image" not in request.FILES:
            obj.mobile_image = ""

        try:
            obj.full_clean()
            obj.save()

            # Schedule old file cleanup after successful commit
            storage = PromotionalBanner.desktop_image.field.storage
            new_desktop_name = obj.desktop_image.name if obj.desktop_image else None
            new_mobile_name = obj.mobile_image.name if obj.mobile_image else None

            files_to_delete = []
            if old_desktop_name and old_desktop_name != new_desktop_name:
                files_to_delete.append(old_desktop_name)
            if old_mobile_name and old_mobile_name != new_mobile_name:
                files_to_delete.append(old_mobile_name)

            if files_to_delete:
                transaction.on_commit(lambda: [
                    storage.delete(f) for f in files_to_delete if storage.exists(f)
                ])

            messages.success(request, f"بنر «{obj.title or obj.pk}» ذخیره شد")
            return redirect("dashboard:banner-list")
        except (ValidationError, IntegrityError) as exc:
            msg = str(exc.message_dict if hasattr(exc, "message_dict") else exc)
            messages.error(request, msg)

    categories = Category.objects.filter(is_active=True).order_by("order", "name")
    return render(request, "dashboard/banner_form.html", {
        "banner": banner, "active_page": "homepage", "categories": categories,
    })


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def banner_delete(request, pk):
    from django.db import transaction

    banner = get_object_or_404(PromotionalBanner, pk=pk)
    desktop_name = banner.desktop_image.name if banner.desktop_image else None
    mobile_name = banner.mobile_image.name if banner.mobile_image else None
    storage = banner.desktop_image.storage

    banner.delete()

    # Delete owned files only after successful DB commit
    def _cleanup():
        if desktop_name and storage.exists(desktop_name):
            storage.delete(desktop_name)
        if mobile_name and storage.exists(mobile_name):
            storage.delete(mobile_name)

    transaction.on_commit(_cleanup)
    messages.success(request, "بنر حذف شد")
    return redirect("dashboard:banner-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def banner_toggle(request, pk):
    banner = get_object_or_404(PromotionalBanner, pk=pk)
    banner.is_active = not banner.is_active
    banner.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if banner.is_active else "غیرفعال"
    messages.info(request, f"بنر {state} شد")
    return redirect("dashboard:banner-list")




# ---------------------------------------------------------------- شبکه‌های اجتماعی

from apps.content.models import SocialLink


@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_list(request):
    links = SocialLink.objects.all().order_by("display_order", "id")
    return render(request, "dashboard/social_links.html", {
        "links": links, "active_page": "social_links",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_form(request, pk=None):
    link = get_object_or_404(SocialLink, pk=pk) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = link or SocialLink()
        obj.platform = request.POST.get("platform", "custom")
        obj.title = request.POST.get("title", "").strip()
        obj.url = request.POST.get("url", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"
        obj.show_in_header = request.POST.get("show_in_header") == "on"
        obj.show_in_footer = request.POST.get("show_in_footer") == "on"

        try:
            obj.full_clean()
            obj.save()
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"لینک «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:social-link-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    platforms = SocialLink.Platform.choices
    return render(request, "dashboard/social_link_form.html", {
        "link": link, "active_page": "social_links", "platforms": platforms,
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_delete(request, pk):
    link = get_object_or_404(SocialLink, pk=pk)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "لینک شبکه اجتماعی",
            "object_name": link.title,
            "cancel_url": reverse("dashboard:social-link-list"),
            "active_page": "social_links",
        })
    title = link.title
    link.delete()
    messages.success(request, f"لینک «{title}» حذف شد")
    return redirect("dashboard:social-link-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def social_link_toggle(request, pk):
    link = get_object_or_404(SocialLink, pk=pk)
    link.is_active = not link.is_active
    link.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if link.is_active else "غیرفعال"
    messages.info(request, f"لینک «{link.title}» {state} شد")
    return redirect("dashboard:social-link-list")




# ---------------------------------------------------------------- مدیریت منوها

from apps.content.models import Menu, MenuItem


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_list(request):
    menus = Menu.objects.annotate(item_count=Count("items")).order_by("location")
    return render(request, "dashboard/menu_list.html", {
        "menus": menus, "active_page": "menus",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_form(request, pk=None):
    menu = get_object_or_404(Menu, pk=pk) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = menu or Menu()
        obj.title = request.POST.get("title", "").strip()
        obj.location = request.POST.get("location", "")
        obj.is_active = request.POST.get("is_active") == "on"

        try:
            obj.full_clean()
            obj.save()
            if pk:
                messages.success(request, f"منوی «{obj.title}» با موفقیت ویرایش شد")
                return redirect("dashboard:menu-list")
            else:
                messages.success(request, f"منوی «{obj.title}» ایجاد شد. اکنون آیتم‌ها را اضافه کنید.")
                return redirect("dashboard:menu-item-list", menu_id=obj.pk)
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            elif "UNIQUE constraint" in str(exc) or "unique" in str(exc).lower():
                msg = "این مکان قبلاً دارای منو است. هر مکان فقط یک منو می‌تواند داشته باشد."
                field_errors = {"location": msg}
            else:
                msg = str(exc)
            messages.error(request, msg)

    locations = Menu.Location.choices
    return render(request, "dashboard/menu_form.html", {
        "menu": menu, "active_page": "menus", "locations": locations,
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_delete(request, pk):
    menu = get_object_or_404(Menu, pk=pk)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "منو",
            "object_name": menu.title,
            "cancel_url": reverse("dashboard:menu-list"),
            "consequence": "تمام آیتم‌های این منو نیز حذف خواهند شد.",
            "active_page": "menus",
        })
    if menu.items.exists():
        messages.error(request, f"منوی «{menu.title}» دارای آیتم است و قابل حذف نیست. ابتدا آیتم‌ها را حذف کنید.")
        return redirect("dashboard:menu-list")
    title = menu.title
    try:
        menu.delete()
    except ProtectedError:
        messages.error(request, f"منوی «{menu.title}» دارای آیتم است و قابل حذف نیست.")
        return redirect("dashboard:menu-list")
    messages.success(request, f"منوی «{title}» حذف شد")
    return redirect("dashboard:menu-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def menu_toggle(request, pk):
    menu = get_object_or_404(Menu, pk=pk)
    menu.is_active = not menu.is_active
    menu.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if menu.is_active else "غیرفعال"
    messages.info(request, f"منوی «{menu.title}» {state} شد")
    return redirect("dashboard:menu-list")


# --- آیتم‌های منو ---


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_list(request, menu_id):
    menu = get_object_or_404(Menu, pk=menu_id)
    items = menu.items.select_related("parent").order_by("parent__display_order", "parent__id", "display_order", "id")
    # Organize: top-level first, then children grouped under parents
    top_items = [i for i in items if i.parent_id is None]
    children_map = {}
    for i in items:
        if i.parent_id:
            children_map.setdefault(i.parent_id, []).append(i)

    organized = []
    for item in top_items:
        organized.append(("top", item))
        for child in children_map.get(item.pk, []):
            organized.append(("child", child))

    return render(request, "dashboard/menu_item_list.html", {
        "menu": menu, "organized_items": organized, "active_page": "menus",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_form(request, menu_id=None, pk=None):
    from apps.catalog.models import Category

    if pk:
        item = get_object_or_404(MenuItem, pk=pk)
        menu = item.menu
    else:
        menu = get_object_or_404(Menu, pk=menu_id)
        item = None

    field_errors = {}

    if request.method == "POST":
        obj = item or MenuItem(menu=menu)
        obj.title = request.POST.get("title", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"
        obj.open_in_new_tab = request.POST.get("open_in_new_tab") == "on"

        # Parent
        parent_id = request.POST.get("parent") or None
        obj.parent_id = int(parent_id) if parent_id else None

        # Destination fields
        obj.destination_type = request.POST.get("destination_type", "none")
        obj.destination_external_url = request.POST.get("destination_external_url", "").strip()
        cat_id = request.POST.get("destination_category") or None
        prod_id = request.POST.get("destination_product") or None
        brand_id = request.POST.get("destination_brand") or None
        obj.destination_category_id = int(cat_id) if cat_id else None
        obj.destination_product_id = int(prod_id) if prod_id else None
        obj.destination_brand_id = int(brand_id) if brand_id else None

        try:
            obj.full_clean()
            obj.save()
            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"آیتم «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:menu-item-list", menu_id=menu.pk)
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    # Parent options: only top-level items of this menu (not the item itself)
    parent_options = menu.items.filter(parent__isnull=True)
    if pk:
        parent_options = parent_options.exclude(pk=pk)

    categories = Category.objects.filter(is_active=True).order_by("order", "name")
    return render(request, "dashboard/menu_item_form.html", {
        "item": item, "menu": menu, "active_page": "menus",
        "parent_options": parent_options, "categories": categories,
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    menu_id = item.menu_id
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "آیتم منو",
            "object_name": item.title,
            "cancel_url": reverse("dashboard:menu-item-list", args=[menu_id]),
            "active_page": "menus",
        })
    try:
        item.delete()
        messages.success(request, f"آیتم «{item.title}» حذف شد")
    except ProtectedError:
        messages.error(request, f"آیتم «{item.title}» دارای زیرآیتم است. ابتدا زیرآیتم‌ها را حذف کنید.")
    return redirect("dashboard:menu-item-list", menu_id=menu_id)


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def menu_item_toggle(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if item.is_active else "غیرفعال"
    messages.info(request, f"آیتم «{item.title}» {state} شد")
    return redirect("dashboard:menu-item-list", menu_id=item.menu_id)




# ---------------------------------------------------------------- تنظیمات فوتر

from apps.content.models import FooterSettings, FooterTrustBadge, FooterPaymentLogo


def _resolve_dashboard_store(request):
    """Store مورد نیاز برای عملیات نوشتنِ داشبورد (تنظیمات/نمادها/لوگوهای
    فوتر/سفارش/پیامک آزمایشی) — نازک‌پوششی روی
    ``apps.stores.resolution.resolve_store_for_service``، همان قانون
    fail-closed مشترک در کل کدبیس."""
    from apps.stores.resolution import resolve_store_for_service

    return resolve_store_for_service(request)


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_settings_page(request):
    fs = FooterSettings.load(store=request.store)
    field_errors = {}

    if request.method == "POST":
        fs.is_enabled = request.POST.get("is_enabled") == "on"
        fs.show_branding = request.POST.get("show_branding") == "on"
        fs.show_logo = request.POST.get("show_logo") == "on"
        fs.description = request.POST.get("description", "").strip()
        fs.show_contact = request.POST.get("show_contact") == "on"
        fs.address = request.POST.get("address", "").strip()
        fs.phone = request.POST.get("phone", "").strip()
        fs.secondary_phone = request.POST.get("secondary_phone", "").strip()
        fs.email = request.POST.get("email", "").strip()
        fs.working_hours = request.POST.get("working_hours", "").strip()
        fs.show_navigation = request.POST.get("show_navigation") == "on"
        fs.show_social_links = request.POST.get("show_social_links") == "on"
        fs.show_newsletter = request.POST.get("show_newsletter") == "on"
        fs.newsletter_title = request.POST.get("newsletter_title", "").strip()
        fs.newsletter_description = request.POST.get("newsletter_description", "").strip()
        fs.show_trust_badges = request.POST.get("show_trust_badges") == "on"
        fs.show_payment_logos = request.POST.get("show_payment_logos") == "on"
        fs.copyright_text = request.POST.get("copyright_text", "").strip()

        try:
            fs.full_clean()
            fs.save()
            messages.success(request, "تنظیمات فوتر ذخیره شد")
            return redirect("dashboard:footer-settings")
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)
            open_sections = {"general"}
            if hasattr(exc, "message_dict"):
                field_section_map = {
                    "address": "contact", "phone": "contact", "secondary_phone": "contact",
                    "email": "contact", "working_hours": "contact",
                    "newsletter_title": "newsletter", "newsletter_description": "newsletter",
                    "copyright_text": "copyright",
                }
                for field in exc.message_dict:
                    if field in field_section_map:
                        open_sections.add(field_section_map[field])
            return render(request, "dashboard/footer_settings.html", {
                "fs": fs, "active_page": "footer", "open_sections": open_sections,
                "field_errors": field_errors,
            })

    return render(request, "dashboard/footer_settings.html", {
        "fs": fs, "active_page": "footer",
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_list(request):
    store = _resolve_dashboard_store(request)
    badges = FooterTrustBadge.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/footer_trust_badges.html", {
        "badges": badges, "active_page": "footer",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_form(request, pk=None):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = badge or FooterTrustBadge(store=store)
        old_image_name = obj.image.name if obj.pk and obj.image else None

        obj.title = request.POST.get("title", "").strip()
        obj.destination_url = request.POST.get("destination_url", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"

        if "image" in request.FILES:
            obj.image = request.FILES["image"]

        try:
            obj.full_clean()
            obj.save()

            # Cleanup old image
            if old_image_name and old_image_name != (obj.image.name if obj.image else ""):
                storage = obj.image.storage
                transaction.on_commit(lambda n=old_image_name, s=storage: (
                    s.delete(n) if s.exists(n) else None
                ))

            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"نماد اعتماد «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:footer-trust-badge-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    return render(request, "dashboard/footer_trust_badge_form.html", {
        "badge": badge, "active_page": "footer",
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_delete(request, pk):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "نماد اعتماد",
            "object_name": badge.title,
            "cancel_url": reverse("dashboard:footer-trust-badge-list"),
            "active_page": "footer",
        })
    image_name = badge.image.name if badge.image else None
    storage = badge.image.storage if badge.image else None
    title = badge.title
    badge.delete()

    if image_name and storage:
        transaction.on_commit(lambda: (
            storage.delete(image_name) if storage.exists(image_name) else None
        ))

    messages.success(request, f"نماد اعتماد «{title}» حذف شد")
    return redirect("dashboard:footer-trust-badge-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def footer_trust_badge_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store)
    badge.is_active = not badge.is_active
    badge.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if badge.is_active else "غیرفعال"
    messages.info(request, f"نماد اعتماد «{badge.title}» {state} شد")
    return redirect("dashboard:footer-trust-badge-list")


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_list(request):
    store = _resolve_dashboard_store(request)
    logos = FooterPaymentLogo.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/footer_payment_logos.html", {
        "logos": logos, "active_page": "footer",
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_form(request, pk=None):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store) if pk else None
    field_errors = {}

    if request.method == "POST":
        obj = logo or FooterPaymentLogo(store=store)
        old_image_name = obj.image.name if obj.pk and obj.image else None

        obj.title = request.POST.get("title", "").strip()
        obj.display_order = int(request.POST.get("display_order", "0") or "0")
        obj.is_active = request.POST.get("is_active") == "on"

        if "image" in request.FILES:
            obj.image = request.FILES["image"]

        try:
            obj.full_clean()
            obj.save()

            # Cleanup old image
            if old_image_name and old_image_name != (obj.image.name if obj.image else ""):
                storage = obj.image.storage
                transaction.on_commit(lambda n=old_image_name, s=storage: (
                    s.delete(n) if s.exists(n) else None
                ))

            action = "ویرایش" if pk else "ایجاد"
            messages.success(request, f"لوگوی پرداخت «{obj.title}» با موفقیت {action} شد")
            return redirect("dashboard:footer-payment-logo-list")
        except (ValidationError, IntegrityError) as exc:
            if hasattr(exc, "message_dict"):
                field_errors = {k: v[0] if isinstance(v, list) else str(v) for k, v in exc.message_dict.items()}
                msg = " ".join(field_errors.values())
            else:
                msg = str(exc)
            messages.error(request, msg)

    return render(request, "dashboard/footer_payment_logo_form.html", {
        "logo": logo, "active_page": "footer",
        "field_errors": field_errors,
    })


@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_delete(request, pk):
    from django.db import transaction

    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store)
    if request.method != "POST":
        return render(request, "dashboard/confirm_delete.html", {
            "object_type": "لوگوی پرداخت",
            "object_name": logo.title,
            "cancel_url": reverse("dashboard:footer-payment-logo-list"),
            "active_page": "footer",
        })
    image_name = logo.image.name if logo.image else None
    storage = logo.image.storage if logo.image else None
    title = logo.title
    logo.delete()

    if image_name and storage:
        transaction.on_commit(lambda: (
            storage.delete(image_name) if storage.exists(image_name) else None
        ))

    messages.success(request, f"لوگوی پرداخت «{title}» حذف شد")
    return redirect("dashboard:footer-payment-logo-list")


@require_POST
@staff_required
@permission_required(CONTENT_MANAGE)
def footer_payment_logo_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store)
    logo.is_active = not logo.is_active
    logo.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if logo.is_active else "غیرفعال"
    messages.info(request, f"لوگوی پرداخت «{logo.title}» {state} شد")
    return redirect("dashboard:footer-payment-logo-list")



# ===========================================================================
# Payment Gateway Configuration (PR1)
# ===========================================================================


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_gateway_config_save(request, gateway_code):
    """ذخیره‌ی پیکربندی یک درگاه پرداخت (Zibal/COD) برای فروشگاه فعلی."""
    from apps.orders.encryption import CredentialEncryptionError, mask_credential
    from apps.orders.gateways import get_adapter, GATEWAY_CHOICES
    from apps.orders.models import PaymentGatewayConfig

    store = _resolve_dashboard_store(request)

    # Validate gateway code
    valid_codes = [code for code, _ in GATEWAY_CHOICES]
    if gateway_code not in valid_codes:
        return HttpResponse(status=404)

    # Get or create config for this store+gateway
    config, _created = PaymentGatewayConfig.objects.get_or_create(
        store=store,
        gateway_code=gateway_code,
        defaults={"display_order": len(valid_codes)},
    )

    adapter = get_adapter(gateway_code)

    # Process form data
    is_active = request.POST.get("is_active") == "on"
    is_sandbox = request.POST.get("is_sandbox") == "on"
    display_title = request.POST.get("display_title", "").strip()
    display_order = request.POST.get("display_order", "0")
    try:
        display_order = int(display_order)
    except (TypeError, ValueError):
        display_order = 0

    # Process credentials (only for gateways that need them)
    credentials = config.get_credentials()  # Start with existing
    credential_errors = []

    for field_name in adapter.required_credentials:
        new_value = request.POST.get(f"credential_{field_name}", "").strip()
        if new_value:
            # New value provided — update
            credentials[field_name] = new_value
        # If empty and existing value exists, keep existing (don't clear on blank)

    # Validate credentials before activation
    if is_active and adapter.required_credentials:
        validation_errors = adapter.validate_credentials(credentials)
        if validation_errors:
            credential_errors = validation_errors
            is_active = False  # Cannot activate with invalid credentials

    # Update config
    config.display_title = display_title
    config.display_order = display_order
    config.is_sandbox = is_sandbox

    if credentials and adapter.required_credentials:
        try:
            config.set_credentials(credentials)
        except CredentialEncryptionError as exc:
            credential_errors.append("خطا در رمزنگاری اعتبارنامه. لطفاً دوباره تلاش کنید.")
            is_active = False

    config.is_active = is_active
    config.save()

    # Build response
    if credential_errors:
        toast_msg = " | ".join(credential_errors)
        toast_type = "err"
    else:
        state = "فعال" if config.is_active else "ذخیره"
        toast_msg = f"پیکربندی {adapter.display_name} با موفقیت {state} شد"
        toast_type = "ok"

    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": toast_msg, "type": toast_type},
        "settings-reload": {},
    })
    return response


@require_POST
@staff_required
@permission_required(PAYMENT_SETTINGS_MANAGE)
def settings_gateway_config_toggle(request, gateway_code):
    """فعال/غیرفعال کردن سریع یک درگاه پیکربندی‌شده."""
    from apps.orders.gateways import get_adapter, GATEWAY_CHOICES
    from apps.orders.models import PaymentGatewayConfig

    store = _resolve_dashboard_store(request)

    valid_codes = [code for code, _ in GATEWAY_CHOICES]
    if gateway_code not in valid_codes:
        return HttpResponse(status=404)

    config = PaymentGatewayConfig.objects.filter(
        store=store, gateway_code=gateway_code
    ).first()

    if config is None:
        return HttpResponse(status=404)

    adapter = get_adapter(gateway_code)

    if config.is_active:
        # Deactivate — always allowed
        config.is_active = False
        config.save(update_fields=["is_active", "updated_at"])
        toast_msg = f"{adapter.display_name} غیرفعال شد"
    else:
        # Activate — only if configured
        if adapter.required_credentials:
            errors = adapter.validate_credentials(config.get_credentials())
            if errors:
                response = HttpResponse(status=204)
                response["HX-Trigger"] = json.dumps({
                    "toast": {"message": "پیکربندی ناقص — ابتدا اعتبارنامه را وارد کنید", "type": "err"},
                })
                return response
        config.is_active = True
        config.save(update_fields=["is_active", "updated_at"])
        toast_msg = f"{adapter.display_name} فعال شد"

    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": toast_msg, "type": "info"},
        "settings-reload": {},
    })
    return response
