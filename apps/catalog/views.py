import json
from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Avg, F, Max, Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.blog.models import BlogPost
from apps.content.models import HeroSlide, PromotionalBanner
from apps.content.services import resolve_destination_url
from apps.customers.models import Customer
from apps.stores.resolution import resolve_store_for_storefront

from .models import Brand, Category, Product, Review
from .services.storefront_variant_service import build_variant_selector_context

BEST_SORT_OPTIONS = {
    "sold": ("-sold_count", "پرفروش‌ترین"),
    "new": ("-created_at", "جدیدترین"),
    "view": ("-views_count", "پربازدید"),
    "disc": ("-discount_percent", "تخفیف‌دار"),
}
DEFAULT_SORT = "sold"

TILE_CLASSES = ["t1", "t2", "t3"]


def _best_products(store, sort_key):
    order_field, _ = BEST_SORT_OPTIONS.get(sort_key, BEST_SORT_OPTIONS[DEFAULT_SORT])
    qs = (
        Product.objects.filter(store=store, status=Product.Status.ACTIVE)
        .select_related("brand").prefetch_related("images")
    )
    if sort_key == "disc":
        qs = qs.filter(discount_percent__gt=0)
    return qs.order_by(order_field)[:8]


def home(request):
    store = resolve_store_for_storefront(request)
    active_products = Product.objects.filter(store=store, status=Product.Status.ACTIVE)

    top_categories = list(
        Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
    )
    icon_categories = (
        Category.objects.filter(store=store, parent__isnull=False, is_active=True)
        .select_related("parent")
        .order_by("order", "name")
    )

    new_products = active_products.select_related("brand").prefetch_related("images").order_by("-created_at")[:8]
    discounted_products = (
        active_products.select_related("brand").prefetch_related("images")
        .filter(discount_percent__gt=0).order_by("-discount_percent")[:6]
    )
    highlight_product = discounted_products.first()
    most_viewed_product = active_products.order_by("-views_count").first()

    stats = active_products.aggregate(avg_rating=Avg("rating"), max_discount=Max("discount_percent"))

    context = {
        "sort_key": DEFAULT_SORT,
        "best_sort_options": BEST_SORT_OPTIONS,
        "best_products": _best_products(store, DEFAULT_SORT),
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
        "hero_slides": HeroSlide.objects.filter(is_active=True).select_related(
            "destination_category", "destination_product", "destination_brand"
        ),
        "promo_banners": PromotionalBanner.objects.filter(is_active=True).select_related(
            "destination_category", "destination_product", "destination_brand"
        ),
    }
    return render(request, "catalog/home.html", context)


def home_best_products(request):
    store = resolve_store_for_storefront(request)
    sort_key = request.GET.get("sort", DEFAULT_SORT)
    if sort_key not in BEST_SORT_OPTIONS:
        sort_key = DEFAULT_SORT
    context = {"products": _best_products(store, sort_key)}
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


def _filtered_products(request, store):
    qs = (
        Product.objects.filter(store=store, status=Product.Status.ACTIVE)
        .select_related("brand", "category")
        .prefetch_related("images")
    )

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
    store = resolve_store_for_storefront(request)
    qs, sort_key, query = _filtered_products(request, store)

    paginator = Paginator(qs, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    filter_categories = Category.objects.filter(store=store, parent__isnull=True, is_active=True).prefetch_related(
        Prefetch("children", queryset=Category.objects.filter(store=store, is_active=True).order_by("order", "name"))
    ).order_by("order", "name")

    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "query": query,
        "sort_key": sort_key,
        "sort_options": LIST_SORT_OPTIONS,
        "filter_categories": filter_categories,
        "brands": Brand.objects.filter(store=store, is_active=True).order_by("name"),
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


def _variant_groups(product):
    groups = {}
    for variant in product.variants.all().order_by("attribute", "value"):
        groups.setdefault(variant.attribute, []).append(variant)
    return groups


def _gallery_slides(product):
    images = list(product.images.all().order_by("order"))
    if images:
        return [
            {
                "type": "image",
                "url": img.image.url,
                "thumb_url": img.thumbnail.url if img.thumbnail else img.image.url,
                "alt": img.alt or product.name,
                # اگر تصویر به یک تنوعِ خاص اختصاص یافته باشد، با انتخابِ همان
                # تنوع در فروشگاه، گالری خودکار به این تصویر سوییچ می‌کند —
                # نگاه کنید به apps.catalog.services.product_image_service.set_image_variant.
                # وقتی تنوعِ انتخاب‌شده تصویرِ اختصاصی ندارد، گالری به همین
                # تصویرِ کاور برمی‌گردد (نه این‌که رویِ تصویرِ تنوعِ قبلی بماند).
                "variant_id": img.variant_id,
                "is_cover": img.is_cover,
            }
            for img in images
        ]

    base_tint = product.tint or "#eceef3"
    pseudo_tints = [base_tint, "#f7f3fe", "#eef0f6", "#f6efe2"]
    emoji = product.icon or "🛍️"
    return [{"type": "emoji", "tint": tint, "emoji": emoji} for tint in pseudo_tints]


def _can_review(request):
    return request.user.is_authenticated and hasattr(request.user, "customer_profile")


def build_product_detail_context(request, product):
    """کانتکستِ کاملِ صفحه‌ی محصول — هم برایِ نمایشِ عمومیِ فروشگاه (``product_detail``)
    و هم برایِ پیش‌نمایشِ مدیرِ فروشگاه (``dashboard:product-preview``، برایِ
    کالاهایِ منتشرنشده) استفاده می‌شود تا منطق هرگز دوباره‌نویسی نشود."""
    store = product.store
    variant_groups = _variant_groups(product)
    spec_variant_summary = {
        attribute: "، ".join(v.value for v in items) for attribute, items in variant_groups.items()
    }

    approved_reviews = product.reviews.filter(is_approved=True).select_related("customer").order_by("-created_at")
    review_count = approved_reviews.count()
    rating_breakdown = []
    for star in range(5, 0, -1):
        count = approved_reviews.filter(rating=star).count()
        pct = round(count * 100 / review_count) if review_count else 0
        rating_breakdown.append({"star": star, "count": count, "pct": pct})

    related_products = (
        Product.objects.filter(store=store, status=Product.Status.ACTIVE, category=product.category)
        .exclude(pk=product.pk)
        .select_related("brand")
        .prefetch_related("images")[:4]
    )

    savings = product.price - product.final_price
    context = {
        "product": product,
        "variant_groups": variant_groups,
        "spec_variant_summary": spec_variant_summary,
        "variant_selector": build_variant_selector_context(product),
        "product_price_json": {
            "price": int(product.final_price), "regular": int(product.price),
            "savings": int(savings), "stock": product.stock, "sku": product.sku,
        },
        "gallery_slides": _gallery_slides(product),
        "approved_reviews": approved_reviews,
        "review_count": review_count,
        "rating_breakdown": rating_breakdown,
        "related_products": related_products,
        "can_review": _can_review(request),
        "savings": savings,
    }
    return context


def product_detail(request, slug):
    store = resolve_store_for_storefront(request)
    product = get_object_or_404(
        Product.objects.select_related("brand", "category", "category__parent", "vendor"),
        slug=slug, store=store, status=Product.Status.ACTIVE,
    )
    Product.objects.filter(pk=product.pk).update(views_count=F("views_count") + 1)
    product.views_count += 1

    context = build_product_detail_context(request, product)
    return render(request, "catalog/product_detail.html", context)


@require_POST
def product_review_create(request, slug):
    store = resolve_store_for_storefront(request)
    product = get_object_or_404(Product, slug=slug, store=store, status=Product.Status.ACTIVE)

    context = {"product": product, "can_review": _can_review(request)}

    if not context["can_review"]:
        return render(request, "catalog/partials/review_form.html", context)

    posted_rating = request.POST.get("rating", "")
    text = request.POST.get("text", "").strip()
    errors = []

    rating = None
    try:
        rating = int(posted_rating)
        if not 1 <= rating <= 5:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("امتیاز باید بین ۱ تا ۵ باشد.")

    if not text:
        errors.append("متن نظر را وارد کنید.")

    if errors:
        context.update({"errors": errors, "posted_rating": posted_rating, "posted_text": text})
        return render(request, "catalog/partials/review_form.html", context)

    Review.objects.create(
        product=product, customer=request.user.customer_profile, rating=rating, text=text, is_approved=False
    )
    context["submitted"] = True
    response = render(request, "catalog/partials/review_form.html", context)
    response["HX-Trigger"] = json.dumps(
        {"toast": {"message": "نظر شما ثبت شد و پس از بررسی نمایش داده می‌شود", "type": "ok"}}
    )
    return response
