import json

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, ProtectedError, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.catalog.models import Category, Product, ProductImage, ProductVariant
from apps.catalog.services.pricing_service import resolve_effective_price
from apps.catalog.services.product_image_service import (
    ProductImageError,
    add_product_image,
    delete_product_image,
    move_product_image,
    set_cover_image,
    update_image_alt,
)
from apps.catalog.services.variant_service import (
    ProductTypeError,
    VariantError,
    bulk_create_variants,
    deactivate_variant,
    delete_variant,
    reorder_variants,
    set_product_type,
    update_variant,
)
from apps.core.color_utils import safe_hex
from apps.core.models import ShopSettings
from apps.core.theme_presets import THEME_PRESETS, matching_preset_key
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, Transaction
from apps.orders.services.order_service import change_order_status
from apps.sms.events import EVENT_VARIABLES
from apps.sms.models import SmsTemplate
from apps.sms.services.sms_service import SmsTemplateError, send_test_sms

from .decorators import staff_required
from .forms import (
    CategoryEditForm,
    FinanceSettingsForm,
    MainCategoryForm,
    ProductForm,
    ProductImageAltForm,
    ProductImageUploadForm,
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
    PRODUCT_STATUS_FILTERS,
    CategoryDeleteError,
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


def admin_login(request):
    """صفحه‌ی ورود اختصاصی پنل مدیریت — مستقل از فروشگاه."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(request.GET.get("next", "/admin-panel/"))

    error = ""
    username = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_staff:
            auth_login(request, user)
            next_url = request.POST.get("next", request.GET.get("next", "/admin-panel/"))
            # Prevent open redirect — ensure next is a relative admin path
            if not next_url.startswith("/admin-panel/"):
                next_url = "/admin-panel/"
            return redirect(next_url)
        elif user is not None and not user.is_staff:
            error = "شما به پنل مدیریت دسترسی ندارید"
        else:
            error = "نام کاربری یا رمز عبور اشتباه است"

    next_url = request.GET.get("next", "/admin-panel/")
    return render(request, "dashboard/login.html", {
        "error": error,
        "username": username,
        "next": next_url,
    })


@staff_required
def dashboard_home(request):
    store = _resolve_dashboard_store(request)
    context = dashboard_service.build_dashboard_context(store)
    context["active_page"] = "dashboard"
    return render(request, "dashboard/dashboard.html", context)


@staff_required
def sales_chart_partial(request):
    range_key = request.GET.get("range", "month")
    if range_key not in VALID_RANGES:
        range_key = "month"
    data, labels = dashboard_service.sales_chart_data(range_key)
    svg = build_line_chart_svg(data, labels)
    return render(request, "dashboard/partials/sales_chart.html", {"svg": svg})


# ---------------------------------------------------------------- محصولات


def _product_list_context(request):
    store = _resolve_dashboard_store(request)
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    status = request.GET.get("status", "")
    return {
        "products": filtered_products(store, q=q, category_id=category_id, status=status),
        "q": q,
        "selected_category": category_id,
        "selected_status": status,
        "category_options": leaf_categories(store),
        "status_options": PRODUCT_STATUS_FILTERS,
    }


@staff_required
def product_list(request):
    context = _product_list_context(request)
    context["active_page"] = "products"
    return render(request, "dashboard/products.html", context)


@staff_required
def product_table(request):
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
    product.price = data["price"]
    product.discount_percent = data["discount_percent"]
    product.stock = data["stock"]
    product.status = data["status"]
    product.icon = data["icon"] or "🛍️"
    product.description = data["description"]
    product.full_clean(exclude=["slug"])
    product.save()
    return product


@staff_required
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
                "price": product.price, "discount_percent": product.discount_percent,
                "stock": product.stock, "status": product.status, "icon": product.icon,
                "description": product.description, "product_type": product.product_type,
            }
        else:
            initial = {"product_type": Product.ProductType.SIMPLE}
        form = ProductForm(instance=product, initial=initial, store=store)

    return render(request, "dashboard/partials/product_form.html", {"form": form, "product": product})


@require_POST
@staff_required
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
def product_images(request, pk):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    return render(request, "dashboard/partials/product_images_modal.html", {
        "product": product, "upload_form": ProductImageUploadForm(),
    })


def _image_list_response(request, product, *, refresh_table=False):
    list_html = render_to_string(
        "dashboard/partials/product_images_list.html", {"product": product}, request=request,
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
def product_image_alt_update(request, pk, image_id):
    store = _resolve_dashboard_store(request)
    product = get_object_or_404(Product, pk=pk, store=store)
    image = get_object_or_404(ProductImage, pk=image_id, product=product)
    form = ProductImageAltForm(request.POST)
    if form.is_valid():
        update_image_alt(image, form.cleaned_data["alt"])
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
    filtered_qs = filtered_qs.order_by("display_order", "attribute", "value")

    paginator = Paginator(filtered_qs, VARIANTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    variants = list(page_obj.object_list)
    for variant in variants:
        variant.effective_price = resolve_effective_price(product, variant)

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
def product_variants(request, pk):
    product = _get_scoped_product(request, pk)
    return render(request, "dashboard/product_variants.html", _variant_page_context(request, product))


@require_POST
@staff_required
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


# --------------------------------------------------------- دسته‌بندی‌ها


def _categories_context(request, *, main_form=None, sub_form=None):
    store = _resolve_dashboard_store(request)
    context = category_tree_context(store)
    context["main_form"] = main_form or MainCategoryForm()
    context["sub_form"] = sub_form or SubCategoryForm(store=store)
    return context


@staff_required
def category_list(request):
    context = _categories_context(request)
    context["active_page"] = "categories"
    return render(request, "dashboard/categories.html", context)


@require_POST
@staff_required
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
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    return {
        "orders": filtered_orders(q=q, status=status),
        "q": q,
        "selected_status": status,
        "status_filters": ORDER_STATUS_FILTERS,
        "status_counts": order_status_counts(),
    }


@staff_required
def order_list(request):
    context = _order_list_context(request)
    context["active_page"] = "orders"
    return render(request, "dashboard/orders.html", context)


@staff_required
def order_table(request):
    return render(request, "dashboard/partials/orders_table_inner.html", _order_list_context(request))


@staff_required
def order_detail(request, code):
    order = get_object_or_404(Order.objects.select_related("customer", "vendor", "shipping_method"), code=code)

    if request.method == "POST":
        to_status = request.POST.get("status", "")
        tracking_code = request.POST.get("tracking_code", "").strip()
        try:
            change_order_status(
                order, to_status, by=request.user, tracking_code=tracking_code,
                store=_resolve_dashboard_store(request),
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
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    orders_qs = filtered_invoices(q=q, status=status)
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
def invoice_list(request):
    context = _invoice_list_context(request)
    context["active_page"] = "invoices"
    return render(request, "dashboard/invoices.html", context)


@staff_required
def invoice_table(request):
    return render(request, "dashboard/partials/invoices_table_inner.html", _invoice_list_context(request))


@staff_required
def invoice_detail(request, code):
    order = get_object_or_404(Order.objects.select_related("customer"), code=code)
    context = {
        "order": order,
        "items": order.items.select_related("product"),
        "active_page": "invoices",
    }
    return render(request, "dashboard/invoice_detail.html", context)


# ---------------------------------------------------------------- پرداخت‌ها


def _payment_list_context(request):
    status = request.GET.get("status", "")
    return {
        "transactions": filtered_transactions(status=status),
        "selected_status": status,
        "status_filters": TRANSACTION_STATUS_FILTERS,
    }


@staff_required
def payment_list(request):
    context = _payment_list_context(request)
    context["active_page"] = "payments"
    return render(request, "dashboard/payments.html", context)


@staff_required
def payment_table(request):
    return render(request, "dashboard/partials/payments_table_inner.html", _payment_list_context(request))


# ---------------------------------------------------------------- مشتریان


def _customer_list_context(request):
    q = request.GET.get("q", "").strip()
    return {"customers": customers_admin_service.annotated_customers(q=q), "q": q}


@staff_required
def customer_list(request):
    context = _customer_list_context(request)
    context["active_page"] = "customers"
    return render(request, "dashboard/customers.html", context)


@staff_required
def customer_table(request):
    return render(request, "dashboard/partials/customers_table_inner.html", _customer_list_context(request))


@staff_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    orders = customers_admin_service.customer_orders(customer)
    context = {
        "customer": customer,
        "orders": orders,
        "paid_total": customers_admin_service.customer_paid_total(orders),
        "active_page": "customers",
    }
    return render(request, "dashboard/customer_detail.html", context)


# -------------------------------------------------------- گزارش‌های حرفه‌ای


@staff_required
def report_list(request):
    context = report_service.build_report_context(request.GET.get("range", "30"))
    context["active_page"] = "reports"
    return render(request, "dashboard/reports.html", context)


@staff_required
def report_partial(request):
    context = report_service.build_report_context(request.GET.get("range", "30"))
    return render(request, "dashboard/partials/reports_body.html", context)


# ------------------------------------------------------------------ تنظیمات


THEME_TOKEN_DEFAULTS = {
    "primary_color": "#6D28D9", "accent_color": "#FF4D77", "secondary_color": "#7C3AED",
    "background_color": "#F7F5FC", "surface_color": "#FFFFFF", "text_color": "#241C3A",
    "muted_text_color": "#8B86A3",
}


def _settings_context(request, *, shop_form=None, finance_form=None, sms_form=None, visual_form=None):
    shop = ShopSettings.load(store=request.store)
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
        "gateways": settings_admin_service.active_gateways_context(),
        "shipping_methods": settings_admin_service.shipping_methods_context(),
        "active_page": "settings",
    }


SETTINGS_SECTIONS = [
    ("general", "اطلاعات فروشگاه", "🏪", "نام، شعار و اطلاعات تماس فروشگاه"),
    ("finance", "مالی و مالیات", "💰", "نرخ مالیات و آستانه‌ی ارسال رایگان"),
    ("delivery-payment", "ارسال و درگاه", "🚚", "روش‌های ارسال و درگاه‌های پرداخت"),
    ("sms", "پیامک", "📲", "اتصال و قالب‌های پیامک"),
    ("appearance", "تم رنگی", "🎨", "پیش‌فرض‌ها و رنگ‌بندی سفارشی فروشگاه"),
]

VALID_SECTION_KEYS = {s[0] for s in SETTINGS_SECTIONS}


@staff_required
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
def settings_shop_info(request):
    form = ShopInfoForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        for field in ["name", "tagline", "contact_phone", "contact_email", "contact_address", "description"]:
            setattr(shop, field, form.cleaned_data[field])
        shop.save()
        messages.success(request, "اطلاعات فروشگاه ذخیره شد")
        return redirect("/admin-panel/settings/?section=general")
    context = _settings_context(request, shop_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "general"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
def settings_finance(request):
    form = FinanceSettingsForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load(store=request.store)
        shop.tax_percent = form.cleaned_data["tax_percent"]
        shop.free_shipping_threshold = form.cleaned_data["free_shipping_threshold"]
        shop.save()
        messages.success(request, "تنظیمات مالی ذخیره شد")
        return redirect("/admin-panel/settings/?section=finance")
    context = _settings_context(request, finance_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "finance"
    return render(request, "dashboard/settings.html", context)


@require_POST
@staff_required
def settings_gateway_toggle(request, pk):
    gateway = settings_admin_service.toggle_gateway(pk)
    state = "فعال" if gateway.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"درگاه «{gateway.name}» {state} شد", "type": "info"}})
    return response


@require_POST
@staff_required
def settings_shipping_toggle(request, pk):
    method = settings_admin_service.toggle_shipping_method(pk)
    state = "فعال" if method.is_active else "غیرفعال"
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({
        "toast": {"message": f"روش ارسال «{method.name}» {state} شد", "type": "info"},
    })
    return response


# --------------------------------------------------------------- هویت بصری


@require_POST
@staff_required
def settings_appearance(request):
    """ذخیره تنظیمات هویت بصری: لوگو، فاوآیکون، توکن‌های رنگی تم؛ یا بازگردانی به پیش‌فرض."""
    from django.db import transaction as db_transaction

    if request.POST.get("action") == "reset":
        shop = ShopSettings.load(store=request.store)
        for field, default in THEME_TOKEN_DEFAULTS.items():
            setattr(shop, field, default)
        shop.save()
        messages.success(request, "رنگ‌بندی به پیش‌فرض بازگردانی شد")
        return redirect("/admin-panel/settings/?section=appearance")

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
        return redirect("/admin-panel/settings/?section=appearance")

    context = _settings_context(request, visual_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "appearance"
    return render(request, "dashboard/settings.html", context)


# --------------------------------------------------------------- پیامک


@require_POST
@staff_required
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
        return redirect("/admin-panel/settings/?section=sms")
    context = _settings_context(request, sms_form=form)
    context["sections"] = SETTINGS_SECTIONS
    context["active_section"] = "sms"
    return render(request, "dashboard/settings.html", context)


@staff_required
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
    return redirect("/admin-panel/settings/?section=sms")


@staff_required
def sms_log_list(request):
    context = {
        "logs": sms_admin_service.filtered_logs(status=request.GET.get("status", "")),
        "selected_status": request.GET.get("status", ""),
        "status_filters": sms_admin_service.LOG_STATUS_FILTERS,
        "active_page": "settings",
    }
    return render(request, "dashboard/sms_logs.html", context)


@staff_required
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
def page_list(request):
    pages = ContentPage.objects.all().order_by("-created_at")
    context = {"pages": pages, "active_page": "pages"}
    return render(request, "dashboard/pages.html", context)


@staff_required
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
def page_delete(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    title = page.title
    page.delete()
    messages.success(request, f"صفحه‌ی «{title}» حذف شد")
    return redirect("dashboard:page-list")


@require_POST
@staff_required
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
def hero_list(request):
    slides = HeroSlide.objects.all().order_by("display_order", "id")
    return render(request, "dashboard/hero_list.html", {"slides": slides, "active_page": "homepage"})


@staff_required
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
def hero_toggle(request, pk):
    slide = get_object_or_404(HeroSlide, pk=pk)
    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if slide.is_active else "غیرفعال"
    messages.info(request, f"اسلاید {state} شد")
    return redirect("dashboard:hero-list")


@staff_required
def banner_list(request):
    banners = PromotionalBanner.objects.all().order_by("display_order", "id")
    return render(request, "dashboard/banner_list.html", {"banners": banners, "active_page": "homepage"})


@staff_required
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
def social_link_list(request):
    links = SocialLink.objects.all().order_by("display_order", "id")
    return render(request, "dashboard/social_links.html", {
        "links": links, "active_page": "social_links",
    })


@staff_required
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
def menu_list(request):
    menus = Menu.objects.annotate(item_count=Count("items")).order_by("location")
    return render(request, "dashboard/menu_list.html", {
        "menus": menus, "active_page": "menus",
    })


@staff_required
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
def menu_toggle(request, pk):
    menu = get_object_or_404(Menu, pk=pk)
    menu.is_active = not menu.is_active
    menu.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if menu.is_active else "غیرفعال"
    messages.info(request, f"منوی «{menu.title}» {state} شد")
    return redirect("dashboard:menu-list")


# --- آیتم‌های منو ---


@staff_required
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
def footer_trust_badge_list(request):
    store = _resolve_dashboard_store(request)
    badges = FooterTrustBadge.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/footer_trust_badges.html", {
        "badges": badges, "active_page": "footer",
    })


@staff_required
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
def footer_trust_badge_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    badge = get_object_or_404(FooterTrustBadge, pk=pk, store=store)
    badge.is_active = not badge.is_active
    badge.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if badge.is_active else "غیرفعال"
    messages.info(request, f"نماد اعتماد «{badge.title}» {state} شد")
    return redirect("dashboard:footer-trust-badge-list")


@staff_required
def footer_payment_logo_list(request):
    store = _resolve_dashboard_store(request)
    logos = FooterPaymentLogo.objects.filter(store=store).order_by("display_order", "id")
    return render(request, "dashboard/footer_payment_logos.html", {
        "logos": logos, "active_page": "footer",
    })


@staff_required
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
def footer_payment_logo_toggle(request, pk):
    store = _resolve_dashboard_store(request)
    logo = get_object_or_404(FooterPaymentLogo, pk=pk, store=store)
    logo.is_active = not logo.is_active
    logo.save(update_fields=["is_active", "updated_at"])
    state = "فعال" if logo.is_active else "غیرفعال"
    messages.info(request, f"لوگوی پرداخت «{logo.title}» {state} شد")
    return redirect("dashboard:footer-payment-logo-list")
