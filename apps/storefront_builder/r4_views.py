import json

from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import appearance_registry, resource_source, section_registry
from .models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from .services import container_service, layout_service, r4_mutation_service, section_structure_service

#: Phase 0/1 R4 Inspector renderer capability — deliberately narrower than
#: SettingsSchema's own ALLOWED_FIELD_TYPES. A schema field of another
#: otherwise-valid schema type (e.g. "color") reaching this Inspector is a
#: developer contract failure, not a merchant free-text fallback.
_INSPECTOR_SUPPORTED_FIELD_TYPES = frozenset({
    "text",
    "rich_text",
    "integer",
    "boolean",
    "choice",
    "appearance_override",
    "resource_source",
})

#: R4 Task 7 — merchant-facing Persian labels for the existing curated
#: type-scale enum (appearance_registry.TYPE_SCALE_CHOICES). Stored values
#: remain the existing enum strings; only the label shown is translated.
_TYPE_SCALE_LABELS_FA = {
    "compact": "فشرده",
    "normal": "معمولی",
    "large": "بزرگ",
}

#: R4 Task 9 — merchant-facing Persian labels for the generic
#: resource_source READ-ONLY summary. Task 9 renders a summary only (no
#: Picker yet — see r4_views.py's Task 9 section); these labels never
#: leave this presentation layer, resource_source.py itself stays UI-agnostic.
_RESOURCE_SOURCE_KIND_LABELS_FA = {
    "product": "محصول",
    "brand": "برند",
    "category": "دسته‌بندی",
    "collection": "کالکشن",
}
_RESOURCE_SOURCE_MODE_LABELS_FA = {
    "auto": "خودکار",
    "manual": "دستی",
}
_RESOURCE_SOURCE_AUTO_RULE_LABELS_FA = {
    "newest": "جدیدترین",
    "discounted": "تخفیف‌دار",
    "best_sellers": "پرفروش‌ترین",
    "most_viewed": "پربازدیدترین",
    "by_category": "بر اساس دسته‌بندی",
    "by_brand": "بر اساس برند",
    "by_collection": "بر اساس کالکشن",
    "all_active": "همه‌ی موارد فعال",
}


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

    # R4 Task 8 — the Structure panel's read projection: the exact visual
    # order Preview renders (Container.order -> Cell.order -> Block.cell_order),
    # not the flat page-level `order`. A pure read — no additional placement
    # mutation beyond the `ensure_page_containers` call already above.
    structure_items = []
    for item in section_structure_service.build_structure_projection(page):
        section_obj = item["section"]
        try:
            item_definition = section_registry.get_definition(section_obj.section_key)
        except section_registry.UnknownSectionTypeError:
            item_definition = None
        structure_items.append({
            "id": section_obj.pk,
            "label": item_definition.label_fa if item_definition else section_obj.section_key,
            "duplicable": bool(item_definition and item_definition.duplicable),
            "removable": bool(item_definition and item_definition.removable),
            "is_locked": section_obj.is_locked,
        })

    # The safe "Add Section" library projection: only definitions allowed
    # on Home and not hidden_from_library — Registry stays the single
    # source of truth, never duplicated into JS.
    structure_library = [
        {
            "category": category,
            "items": [{"key": d.key, "label": d.label_fa} for d in members],
        }
        for category, members in section_registry.list_library_groups(
            page_type=StorefrontPage.PageType.HOME,
        )
    ]

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
            "structure_items": structure_items,
            "structure_library": structure_library,
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

    # R4 Task 7 — the Inspector needs to show what an appearance_override
    # field would inherit while disabled. Pass only the safe typed
    # projection the widget actually renders (font/type_scale), never the
    # whole arbitrary appearance_config.
    global_appearance = draft.effective_appearance_config()
    inherited_appearance_by_field = {
        field.key: {
            "font": global_appearance.get("font"),
            "type_scale": global_appearance.get("type_scale"),
        }
        for field in schema.fields
        if field.field_type == "appearance_override"
    }

    # R4 Task 9 — a resource_source field's CURRENT value must be projected
    # from the real legacy Section.settings (data_source/source_id/
    # product_ids, or brand_ids) through the compatibility adapter, never
    # blindly shown as the schema default — a Product already configured
    # as manual/(7, 3) must project as exactly that, not "auto/newest".
    # Task 9 renders a clean READ-ONLY summary only (no Picker yet).
    resource_source_summary = None
    for field in schema.fields:
        if field.field_type != "resource_source":
            continue
        try:
            projected_source = resource_source.resource_source_from_section_settings(
                section.section_key, current_settings,
            )
        except resource_source.ResourceSourceError:
            continue
        field_values[field.key] = resource_source.serialize_resource_source(projected_source)
        resource_source_summary = {
            "kind_label": _RESOURCE_SOURCE_KIND_LABELS_FA.get(projected_source.kind, projected_source.kind),
            "mode_label": _RESOURCE_SOURCE_MODE_LABELS_FA.get(projected_source.mode, projected_source.mode),
            "auto_rule_label": (
                _RESOURCE_SOURCE_AUTO_RULE_LABELS_FA.get(projected_source.auto_rule, projected_source.auto_rule)
                if projected_source.auto_rule else None
            ),
            "manual_count": len(projected_source.manual_ids),
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
            "appearance_font_choices": appearance_registry.FONT_CHOICES,
            "appearance_type_scale_choices": [
                (value, _TYPE_SCALE_LABELS_FA.get(value, value))
                for value in appearance_registry.TYPE_SCALE_CHOICES
            ],
            "inherited_appearance_by_field": inherited_appearance_by_field,
            "resource_source_summary": resource_source_summary,
        },
    )
