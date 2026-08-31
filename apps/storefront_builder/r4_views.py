import json

from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import section_registry
from .models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from .services import container_service, layout_service, r4_mutation_service

#: Phase 0 R4 Inspector renderer capability — deliberately narrower than
#: SettingsSchema's own ALLOWED_FIELD_TYPES. A schema field of another
#: otherwise-valid schema type (e.g. "color") reaching this Inspector is a
#: developer contract failure, not a merchant free-text fallback.
_INSPECTOR_SUPPORTED_FIELD_TYPES = frozenset({
    "text",
    "rich_text",
    "integer",
    "boolean",
    "choice",
})


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

    # The shell has no <form>/{% csrf_token %} of its own, so the browser
    # mutation client (r4_editor.js) has no other trigger to guarantee a
    # csrftoken cookie exists before its first POST to the Task 5 endpoint.
    get_token(request)

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


@require_GET
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_section_inspector(request, pk):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    # The currently active Draft pointer only — never resolved/switched
    # here (see r4_mutation_service.apply_mutation for the same rule).
    draft = layout.draft_version
    if draft is None or draft.status != StorefrontLayoutVersion.Status.DRAFT:
        raise Http404

    try:
        section = StorefrontSection.objects.select_related("page__version").get(
            pk=pk, page__version=draft,
        )
    except StorefrontSection.DoesNotExist:
        raise Http404

    try:
        definition = section_registry.get_definition(section.section_key)
    except ValueError:
        raise Http404

    schema = definition.settings_schema
    if schema is None:
        raise Http404

    for field in schema.fields:
        if field.field_type not in _INSPECTOR_SUPPORTED_FIELD_TYPES:
            raise ImproperlyConfigured(
                f"R4 Inspector (Phase 0) cannot render field_type={field.field_type!r} "
                f"for key={field.key!r} on section_key={section.section_key!r}"
            )

    basic_fields = tuple(field for field in schema.fields if field.group == "basic")
    advanced_fields = tuple(field for field in schema.fields if field.group == "advanced")
    current_settings = section.settings or {}
    field_values = {
        field.key: current_settings.get(field.key, field.default)
        for field in schema.fields
    }

    return render(
        request,
        "dashboard/storefront_builder/r4/partials/section_inspector.html",
        {
            "section": section,
            "definition": definition,
            "basic_fields": basic_fields,
            "advanced_fields": advanced_fields,
            "field_values": field_values,
        },
    )
