import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from .models import StorefrontPage
from .services import container_service, layout_service, r4_mutation_service


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


def _is_strict_int(value: object) -> bool:
    return type(value) is int


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_mutation(request):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "code": "malformed_json"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "code": "invalid_request_shape"}, status=400)

    base_revision = payload.get("base_revision")
    if not _is_strict_int(base_revision) or base_revision < 0:
        return JsonResponse({"ok": False, "code": "invalid_base_revision"}, status=400)

    mutation = payload.get("mutation")
    if not isinstance(mutation, dict):
        return JsonResponse({"ok": False, "code": "invalid_mutation"}, status=400)

    mutation_type = mutation.get("type")
    if not isinstance(mutation_type, str) or not mutation_type:
        return JsonResponse({"ok": False, "code": "invalid_mutation_type"}, status=400)

    try:
        new_revision = r4_mutation_service.apply_mutation(
            store=store, actor=request.user, base_revision=base_revision, mutation=mutation,
        )
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True, "new_revision": new_revision, "mutation_type": mutation_type})
