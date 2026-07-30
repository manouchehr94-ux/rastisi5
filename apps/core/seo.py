"""SEOِ فروشگاهیِ tenant-safe (Checkpoint 6، ADR-90): sitemap و robots که
به Storeِ resolve‌شده از Hostِ درخواست محدودند — هرگز URLِ فروشگاهِ دیگر یا
کالای پیش‌نویس منتشر نمی‌کنند.

چون چارچوبِ ``django.contrib.sites`` نصب نیست، این‌ها به‌جای
``django.contrib.sitemaps`` (که به Site وابسته است) view‌هایِ سبکِ
request-scoped‌اند: دامنه‌یِ canonical همان Hostِ tenant است."""

from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.content.models import ContentPage
from apps.stores.resolution import resolve_store_for_service

#: بیشینه‌ی URLهایِ هر بخش در sitemap — کرانه‌دار تا کاتالوگِ بزرگ سرریز نکند.
SITEMAP_LIMIT = 5000


def _abs(request, path: str) -> str:
    """URLِ مطلق روی همان Hostِ درخواست (دامنه‌یِ tenant)."""
    return request.build_absolute_uri(path)


def _sitemap_entries(request, store):
    """فهرستِ (loc, lastmod) برایِ محتوایِ عمومیِ این Store."""
    entries = [{"loc": _abs(request, reverse("catalog:home")), "lastmod": None, "priority": "1.0"}]
    entries.append({"loc": _abs(request, reverse("catalog:product-list")), "lastmod": None, "priority": "0.8"})

    categories = (
        Category.objects.filter(store=store, is_active=True)
        .order_by("order", "name")[:SITEMAP_LIMIT]
    )
    for cat in categories:
        loc = _abs(request, reverse("catalog:product-list")) + f"?category={cat.slug}"
        entries.append({"loc": loc, "lastmod": cat.updated_at, "priority": "0.6"})

    products = (
        Product.objects.filter(store=store, status=Product.Status.ACTIVE)
        .order_by("-updated_at")[:SITEMAP_LIMIT]
    )
    for product in products:
        loc = _abs(request, reverse("catalog:product-detail", args=[product.slug]))
        entries.append({"loc": loc, "lastmod": product.updated_at, "priority": "0.7"})

    # صفحاتِ محتوایی (CMS) در این کدبیس سراسری‌اند و همان‌طور که ``page_detail``
    # سرو می‌کند فقط بر اساسِ انتشار فیلتر می‌شوند.
    pages = ContentPage.objects.filter(status=ContentPage.Status.PUBLISHED).order_by("slug")[:SITEMAP_LIMIT]
    for page in pages:
        loc = _abs(request, reverse("content:page-detail", args=[page.slug]))
        entries.append({"loc": loc, "lastmod": getattr(page, "updated_at", None), "priority": "0.4"})

    return entries


def sitemap_xml(request):
    """sitemap.xmlِ محدود به این Store."""
    store = resolve_store_for_service(request)
    entries = _sitemap_entries(request, store)
    return render(
        request, "seo/sitemap.xml", {"entries": entries}, content_type="application/xml",
    )


def robots_txt(request):
    """robots.txt — مسیرهایِ خصوصی (سبد/تسویه/حساب) را از ایندکس کنار می‌گذارد و
    به sitemapِ همین دامنه اشاره می‌کند."""
    lines = [
        "User-agent: *",
        "Disallow: /cart/",
        "Disallow: /checkout/",
        "Disallow: /account/",
        "Disallow: /admin/",
        "Disallow: /admin-portal/",
        "Disallow: /admin-panel/",
        f"Sitemap: {_abs(request, reverse('sitemap-xml'))}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
