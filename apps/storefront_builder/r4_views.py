from django.http import Http404
from django.shortcuts import render

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from .models import StorefrontPage
from .services import container_service, layout_service


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_editor(request):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    draft = layout_service.get_or_create_draft(store, user=request.user)
    page = draft.get_page(StorefrontPage.PageType.HOME)
    container_service.ensure_page_containers(page)
    sections = page.sections.select_related("cell", "cell__container").order_by("order", "id")
    return render(
        request,
        "dashboard/storefront_builder/r4/editor.html",
        {
            "active_page": "storefront_builder",
            "layout": layout,
            "draft": draft,
            "page": page,
            "sections": sections,
            "r4_edit_revision": draft.edit_revision,
        },
    )
