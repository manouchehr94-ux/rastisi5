from datetime import timedelta

from django.db.models import Avg, Max
from django.shortcuts import render
from django.utils import timezone

from apps.blog.models import BlogPost
from apps.customers.models import Customer

from .models import Category, Product

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
