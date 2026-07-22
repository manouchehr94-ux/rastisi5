import json

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Product

from .models import Wishlist


def _can_use_wishlist(request):
    return request.user.is_authenticated and hasattr(request.user, "customer_profile")


def wishlist_list(request):
    can_view = _can_use_wishlist(request)
    products = []
    if can_view:
        items = (
            Wishlist.objects.filter(customer=request.user.customer_profile)
            .select_related("product", "product__brand")
            .order_by("-created_at")
        )
        products = [item.product for item in items]
    return render(request, "customers/wishlist.html", {"products": products, "can_view": can_view})


@require_POST
def wishlist_toggle(request, slug):
    product = get_object_or_404(Product, slug=slug, status=Product.Status.ACTIVE)

    if not _can_use_wishlist(request):
        response = render(request, "customers/partials/wishlist_button.html", {"product": product})
        response["HX-Trigger"] = json.dumps({
            "toast": {"message": "برای افزودن به علاقه‌مندی‌ها ابتدا وارد حساب کاربری شوید", "type": "info"},
            "open-login": {},
        })
        return response

    customer = request.user.customer_profile
    existing = Wishlist.objects.filter(customer=customer, product=product).first()
    if existing:
        existing.delete()
        message = "از علاقه‌مندی‌ها حذف شد"
    else:
        Wishlist.objects.create(customer=customer, product=product)
        message = "به علاقه‌مندی‌ها اضافه شد ❤️"

    wishlisted_ids = set(Wishlist.objects.filter(customer=customer).values_list("product_id", flat=True))
    response = render(
        request, "customers/partials/wishlist_button.html",
        {"product": product, "wishlisted_product_ids": wishlisted_ids},
    )
    response["HX-Trigger"] = json.dumps({"toast": {"message": message, "type": "ok"}})
    return response
