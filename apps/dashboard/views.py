import json

from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.catalog.models import Category, Product

from .decorators import staff_required
from .forms import CategoryEditForm, MainCategoryForm, ProductForm, SubCategoryForm
from .services import dashboard_service
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
