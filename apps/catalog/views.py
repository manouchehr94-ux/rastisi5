from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Avg, Max, Prefetch, Q
from django.shortcuts import render
from django.utils import timezone

from apps.blog.models import BlogPost
from apps.customers.models import Customer

from .models import Brand, Category, Product

BEST_SORT_OPTIONS = {
    "sold": ("-sold_count", "پرفروش‌ترین"),
    "new": ("-created_at", "جدیدترین"),
    "view": ("-views_count", "پربازدید"),
    "disc": ("-discount_percent", "تخفیف‌دار"),
}
DEFAULT_SORT = "sold"

TILE_CLASSES = ["t1", "t2", "t3"]


def _best_products(sort_key):
    order_field, _ = BEST_SORT_OPTIONS.get(sort_key, BEST_SORT_OPTIONS[DEFAULT_SORT])
    qs = Product.objects.filter(status=Product.Status.ACTIVE).select_related("brand")
    if sort_key == "disc":
        qs = qs.filter(discount_percent__gt=0)
    return qs.order_by(order_field)[:8]


def home(request):
    active_products = Product.objects.filter(status=Product.Status.ACTIVE)

    top_categories = list(Category.objects.filter(parent__isnull=True, is_active=True).order_by("order", "name"))
    icon_categories = (
        Category.objects.filter(parent__isnull=False, is_active=True)
        .select_related("parent")
        .order_by("order", "name")
    )

    new_products = active_products.select_related("brand").order_by("-created_at")[:8]
    discounted_products = (
        active_products.select_related("brand").filter(discount_percent__gt=0).order_by("-discount_percent")[:6]
    )
    highlight_product = discounted_products.first()
    most_viewed_product = active_products.order_by("-views_count").first()

    stats = active_products.aggregate(avg_rating=Avg("rating"), max_discount=Max("discount_percent"))

    context = {
        "sort_key": DEFAULT_SORT,
        "best_sort_options": BEST_SORT_OPTIONS,
        "best_products": _best_products(DEFAULT_SORT),
        "top_categories": top_categories,
        "tiles": list(zip(top_categories[:3], TILE_CLASSES)),
        "cream_category": top_categories[3] if len(top_categories) > 3 else None,
        "icon_categories": icon_categories,
        "new_products": new_products,
        "discounted_products": discounted_products,
        "highlight_product": highlight_product,
        "most_viewed_product": most_viewed_product,
        "customers_count": Customer.objects.count(),
        "avg_rating": stats["avg_rating"] or 0,
        "max_discount": stats["max_discount"] or 0,
        "blog_posts": BlogPost.objects.order_by("-published_at")[:5],
        "special_offer_deadline": (timezone.now() + timedelta(hours=8)).isoformat(),
    }
    return render(request, "catalog/home.html", context)


def home_best_products(request):
    sort_key = request.GET.get("sort", DEFAULT_SORT)
    if sort_key not in BEST_SORT_OPTIONS:
        sort_key = DEFAULT_SORT
    context = {"products": _best_products(sort_key)}
    return render(request, "catalog/partials/product_grid.html", context)


PRODUCTS_PER_PAGE = 12

LIST_SORT_OPTIONS = {
    "newest": ("-created_at", "جدیدترین"),
    "price_asc": ("price", "ارزان‌ترین"),
    "price_desc": ("-price", "گران‌ترین"),
    "popular": ("-sold_count", "محبوب‌ترین"),
    "rating": ("-rating", "بیشترین امتیاز"),
}
DEFAULT_LIST_SORT = "newest"


def _filtered_products(request):
    qs = Product.objects.filter(status=Product.Status.ACTIVE).select_related("brand", "category")

    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(brand__name__icontains=query) | Q(category__name__icontains=query)
        ).distinct()

    category_slug = request.GET.get("category", "").strip()
    if category_slug:
        qs = qs.filter(Q(category__slug=category_slug) | Q(category__parent__slug=category_slug))

    brand_slug = request.GET.get("brand", "").strip()
    if brand_slug:
        qs = qs.filter(brand__slug=brand_slug)

    min_price = request.GET.get("min_price", "").strip()
    if min_price.isdigit():
        qs = qs.filter(price__gte=int(min_price))

    max_price = request.GET.get("max_price", "").strip()
    if max_price.isdigit():
        qs = qs.filter(price__lte=int(max_price))

    if request.GET.get("discounted") == "1":
        qs = qs.filter(discount_percent__gt=0)

    sort_key = request.GET.get("sort", DEFAULT_LIST_SORT)
    if sort_key not in LIST_SORT_OPTIONS:
        sort_key = DEFAULT_LIST_SORT
    order_field, _ = LIST_SORT_OPTIONS[sort_key]
    qs = qs.order_by(order_field, "id")

    return qs, sort_key, query


def _querystring_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def product_list(request):
    qs, sort_key, query = _filtered_products(request)

    paginator = Paginator(qs, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    filter_categories = Category.objects.filter(parent__isnull=True, is_active=True).prefetch_related(
        Prefetch("children", queryset=Category.objects.filter(is_active=True).order_by("order", "name"))
    ).order_by("order", "name")

    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "query": query,
        "sort_key": sort_key,
        "sort_options": LIST_SORT_OPTIONS,
        "filter_categories": filter_categories,
        "brands": Brand.objects.order_by("name"),
        "selected_category": request.GET.get("category", "").strip(),
        "selected_brand": request.GET.get("brand", "").strip(),
        "min_price": request.GET.get("min_price", "").strip(),
        "max_price": request.GET.get("max_price", "").strip(),
        "discounted_only": request.GET.get("discounted") == "1",
        "querystring": _querystring_without_page(request),
    }

    if request.headers.get("HX-Request") == "true":
        return render(request, "catalog/partials/product_list_results.html", context)
    return render(request, "catalog/product_list.html", context)
