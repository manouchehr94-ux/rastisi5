from .models import ContentPage, Menu, MenuItem
from .services import resolve_destination_url


def footer_pages(request):
    """صفحات محتوایی منتشرشده که باید در فوتر نمایش داده شوند."""
    pages = ContentPage.objects.filter(
        status=ContentPage.Status.PUBLISHED, show_in_footer=True
    ).only("title", "slug", "footer_column").order_by("display_order", "title")

    quick_access = [p for p in pages if p.footer_column == ContentPage.FooterColumn.QUICK_ACCESS]
    customer_service = [p for p in pages if p.footer_column == ContentPage.FooterColumn.CUSTOMER_SERVICE]

    return {
        "footer_pages_quick_access": quick_access,
        "footer_pages_customer_service": customer_service,
    }


def _build_menu_tree(menu):
    """ساخت درخت آیتم‌های فعال منو با URL حل‌شده — بدون N+1.

    آیتم‌ها از queryset prefetch شده خوانده می‌شوند (فقط فعال‌ها).
    """
    if menu is None:
        return None

    # Use the prefetched items (already filtered to is_active=True)
    items = list(menu.items.all())

    # Build tree: top-level + children
    top_items = []
    children_map = {}
    for item in items:
        if item.parent_id is None:
            top_items.append(item)
        else:
            children_map.setdefault(item.parent_id, []).append(item)

    tree = []
    for item in top_items:
        url = resolve_destination_url(item)
        children = []
        for child in children_map.get(item.pk, []):
            child_url = resolve_destination_url(child)
            if child_url:
                children.append({
                    "title": child.title,
                    "url": child_url,
                    "open_in_new_tab": child.open_in_new_tab,
                })
        # Include item if it has a URL or has renderable children
        if url or children:
            tree.append({
                "title": item.title,
                "url": url,  # May be None for non-clickable parent headings
                "open_in_new_tab": item.open_in_new_tab,
                "children": children,
            })

    return {"title": menu.title, "items": tree} if tree else None


def navigation_menus(request):
    """منوهای ناوبری فعال فروشگاه — هدر، فوتر، موبایل.

    استراتژی Query:
    - ۱ query برای منوهای فعال
    - ۱ query برای آیتم‌های فعال با JOIN مقصدها (select_related)
    جمعاً: ۲ query مستقل از تعداد منوها و آیتم‌ها.
    """
    from django.db.models import Prefetch

    items_qs = MenuItem.objects.filter(is_active=True).select_related(
        "parent", "destination_category", "destination_product", "destination_brand",
    ).order_by("display_order", "id")

    active_menus = {
        m.location: m
        for m in Menu.objects.filter(is_active=True).prefetch_related(
            Prefetch("items", queryset=items_qs),
        )
    }

    return {
        "NAV_HEADER": _build_menu_tree(active_menus.get("header")),
        "NAV_FOOTER_1": _build_menu_tree(active_menus.get("footer_1")),
        "NAV_FOOTER_2": _build_menu_tree(active_menus.get("footer_2")),
        "NAV_FOOTER_3": _build_menu_tree(active_menus.get("footer_3")),
        "NAV_MOBILE": _build_menu_tree(active_menus.get("mobile")),
    }
