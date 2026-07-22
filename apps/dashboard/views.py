import json

from django.contrib import messages
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.catalog.models import Category, Product
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.orders.models import Order, Transaction
from apps.orders.services.order_service import change_order_status

from .decorators import staff_required
from .forms import (
    CategoryEditForm,
    FinanceSettingsForm,
    MainCategoryForm,
    ProductForm,
    ShopInfoForm,
    SubCategoryForm,
)
from .services import customers_admin_service, dashboard_service, report_service, settings_admin_service
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


@staff_required
def dashboard_home(request):
    context = dashboard_service.build_dashboard_context()
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
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    status = request.GET.get("status", "")
    return {
        "products": filtered_products(q=q, category_id=category_id, status=status),
        "q": q,
        "selected_category": category_id,
        "selected_status": status,
        "category_options": leaf_categories(),
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


def _save_product(form, product):
    data = form.cleaned_data
    if product is None:
        product = Product(vendor=default_vendor())
        product.slug = generate_unique_slug(Product, data["name"])
    product.name = data["name"]
    product.sku = data["sku"]
    product.category = data["category"]
    product.price = data["price"]
    product.discount_percent = data["discount_percent"]
    product.stock = data["stock"]
    product.status = data["status"]
    product.icon = data["icon"] or "🛍️"
    product.description = data["description"]
    product.save()
    return product


@staff_required
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None

    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            _save_product(form, product)
            table_html = render_to_string(
                "dashboard/partials/products_table_inner.html", _product_list_context(request), request=request,
            )
            response = render(request, "dashboard/partials/oob_wrap.html", {
                "target_id": "productsTableWrap", "inner_html": table_html,
            })
            action = "ویرایش" if product else "افزوده"
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
                "description": product.description,
            }
        form = ProductForm(instance=product, initial=initial)

    return render(request, "dashboard/partials/product_form.html", {"form": form, "product": product})


@require_POST
@staff_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    name = product.name
    product.delete()
    response = render(request, "dashboard/partials/products_table_inner.html", _product_list_context(request))
    response["HX-Trigger"] = json.dumps({"toast": {"message": f"کالای «{name}» حذف شد", "type": "info"}})
    return response


# --------------------------------------------------------- دسته‌بندی‌ها


def _categories_context(request, *, main_form=None, sub_form=None):
    context = category_tree_context()
    context["main_form"] = main_form or MainCategoryForm()
    context["sub_form"] = sub_form or SubCategoryForm()
    return context


@staff_required
def category_list(request):
    context = _categories_context(request)
    context["active_page"] = "categories"
    return render(request, "dashboard/categories.html", context)


@require_POST
@staff_required
def category_add_main(request):
    form = MainCategoryForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            name=name, icon=form.cleaned_data["icon"] or "📁",
            slug=generate_unique_slug(Category, name),
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
    form = SubCategoryForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data["name"]
        Category.objects.create(
            name=name, icon=form.cleaned_data["icon"], parent=form.cleaned_data["parent"],
            slug=generate_unique_slug(Category, name),
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
    category = get_object_or_404(Category, pk=pk)

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
    category = get_object_or_404(Category, pk=pk)
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
        try:
            change_order_status(order, to_status, by=request.user)
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


def _settings_context(request, *, shop_form=None, finance_form=None):
    shop = ShopSettings.load()
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
        "gateways": settings_admin_service.active_gateways_context(),
        "shipping_methods": settings_admin_service.shipping_methods_context(),
        "active_page": "settings",
    }


@staff_required
def settings_home(request):
    return render(request, "dashboard/settings.html", _settings_context(request))


@require_POST
@staff_required
def settings_shop_info(request):
    form = ShopInfoForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load()
        for field in ["name", "tagline", "contact_phone", "contact_email", "contact_address", "description"]:
            setattr(shop, field, form.cleaned_data[field])
        shop.save()
        messages.success(request, "اطلاعات فروشگاه ذخیره شد")
        return redirect("dashboard:settings")
    return render(request, "dashboard/settings.html", _settings_context(request, shop_form=form))


@require_POST
@staff_required
def settings_finance(request):
    form = FinanceSettingsForm(request.POST)
    if form.is_valid():
        shop = ShopSettings.load()
        shop.tax_percent = form.cleaned_data["tax_percent"]
        shop.free_shipping_threshold = form.cleaned_data["free_shipping_threshold"]
        shop.save()
        messages.success(request, "تنظیمات مالی ذخیره شد")
        return redirect("dashboard:settings")
    return render(request, "dashboard/settings.html", _settings_context(request, finance_form=form))


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
