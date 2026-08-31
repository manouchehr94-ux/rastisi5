"""R4 Task 5 — the single optimistic mutation boundary for the R4 editor.

One transaction: lock the Store's ``StorefrontLayout``, resolve its
currently-active Draft (``layout.draft_version`` — never silently
switched/created here, see ``layout_service.get_or_create_draft`` for that),
compare ``base_revision``, dispatch exactly one allowlisted mutation type,
increment ``edit_revision`` once, and record history through the existing
``edit_history_service`` contract. R3 never calls this module.
"""

from __future__ import annotations

from django.db import transaction

from apps.storefront_builder import resource_source, section_registry
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import edit_history_service, section_structure_service
from apps.storefront_builder.settings_schema import clean_section_schema_patch


class R4MutationError(ValueError):
    pass


class R4StaleRevision(R4MutationError):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("stale_revision")


_MUTATION_HISTORY_LABELS = {
    "section.update_settings": "ویرایش تنظیمات بخش",
    "section.add": "افزودن بخش",
    "section.remove": "حذف بخش",
    "section.duplicate": "تکرار بخش",
    "section.move": "جابه‌جایی بخش",
}


def _history_label(mutation: dict) -> str:
    return _MUTATION_HISTORY_LABELS.get(mutation.get("type"), "ویرایش R4")


def _is_strict_int(value: object) -> bool:
    return type(value) is int


def _require_owned_resource(model, *, store, source_id: int) -> None:
    """Fail closed: a foreign-Store id and a nonexistent id both simply
    fail this single Store-scoped ``exists()`` check — never a second
    query against another Store to tell them apart."""
    if not model.objects.filter(store=store, pk=source_id).exists():
        raise R4MutationError("invalid_resource_ownership")


def _validate_resource_source_ownership(*, store, source: "resource_source.ResourceSource") -> None:
    """R4 Task 10 (Section 8) — a Store-scoped Picker search endpoint alone
    does not stop a client from POSTing an arbitrary foreign-Store id
    straight to this mutation endpoint. Every manual id / auto source_id a
    ``source`` patch actually references must belong to the current Store
    BEFORE the settings are persisted."""
    # Imported here, not at module scope: resource_source.py itself must
    # stay a pure, DB-free domain module (Task 9's hard rule) — the DB
    # lookups this ownership check needs live only in this service.
    from apps.catalog.models import Brand, Category, MerchantCollection
    from apps.catalog.services.collection_service import searchable_products

    if source.kind == "product":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_ids = set(
                searchable_products(store).filter(pk__in=source.manual_ids).values_list("pk", flat=True)
            )
            if owned_ids != set(source.manual_ids):
                raise R4MutationError("invalid_resource_ownership")
            return
        if source.auto_rule == "by_category":
            _require_owned_resource(Category, store=store, source_id=source.auto_parameters["source_id"])
        elif source.auto_rule == "by_brand":
            _require_owned_resource(Brand, store=store, source_id=source.auto_parameters["source_id"])
        elif source.auto_rule == "by_collection":
            _require_owned_resource(MerchantCollection, store=store, source_id=source.auto_parameters["source_id"])
        # newest/discounted/best_sellers/most_viewed reference no specific
        # resource id — nothing to own-check.
        return

    if source.kind == "brand":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_count = Brand.objects.filter(store=store, pk__in=source.manual_ids).count()
            if owned_count != len(set(source.manual_ids)):
                raise R4MutationError("invalid_resource_ownership")
        # auto_rule == "all_active" references no specific resource id.
        return

    # category/collection kinds are not exposed by the Task 10 UI and carry
    # no ownership rule yet — defensively a no-op rather than a false reject.


def _apply_section_update_settings(*, store, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    patch = mutation.get("patch")

    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    if not isinstance(patch, dict):
        raise R4MutationError("invalid_patch")

    # Scoped through the locked, active Draft — never by bare pk — so a
    # section belonging to another Store, or to a Published/non-active
    # version of THIS Store, is indistinguishable from "does not exist".
    try:
        section = StorefrontSection.objects.select_for_update().get(
            pk=section_id, page__version=draft,
        )
    except StorefrontSection.DoesNotExist:
        raise R4MutationError("section_not_found") from None

    try:
        definition = section_registry.get_definition(section.section_key)
    except ValueError:
        raise R4MutationError("unknown_section_type") from None

    if definition.settings_schema is None:
        raise R4MutationError("section_not_schema_enabled")

    # Narrowly scoped: covers both SettingsSchemaError (schema cleaning)
    # and a plain ValueError from the legacy validator bridge that
    # clean_section_schema_patch calls internally — one stable external
    # code either way, never the internal validator's own message text.
    try:
        cleaned = clean_section_schema_patch(definition, patch, section.settings or {})
    except ValueError as exc:
        raise R4MutationError("invalid_settings") from exc

    # R4 Task 10 — ownership is only ever validated when THIS mutation's
    # raw patch actually touches "source"; a stale/deleted legacy reference
    # left over from before Task 10 must never turn an unrelated field edit
    # into a failure (Section 10's explicit backward-compatibility rule).
    # Checked AFTER schema cleaning (the shape is already trustworthy) but
    # BEFORE section.settings is assigned/saved, so a rejection here rolls
    # back cleanly with no settings/revision/history change.
    if "source" in patch:
        try:
            projected_source = resource_source.resource_source_from_section_settings(
                section.section_key, cleaned,
            )
        except resource_source.ResourceSourceError:
            projected_source = None
        if projected_source is not None:
            _validate_resource_source_ownership(store=store, source=projected_source)

    section.settings = cleaned
    section.save(update_fields=["settings"])


def _apply_section_add(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_key = mutation.get("section_key")
    if not isinstance(section_key, str) or not section_key:
        raise R4MutationError("invalid_section_key")
    try:
        section_structure_service.add_section(draft=draft, section_key=section_key)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _apply_section_remove(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    try:
        section_structure_service.remove_section(draft=draft, section_id=section_id)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _apply_section_duplicate(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    try:
        section_structure_service.duplicate_section(draft=draft, section_id=section_id)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _apply_section_move(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    section_id = mutation.get("section_id")
    direction = mutation.get("direction")
    if not _is_strict_int(section_id):
        raise R4MutationError("invalid_section_id")
    if not isinstance(direction, str):
        raise R4MutationError("invalid_direction")
    try:
        section_structure_service.move_section(draft=draft, section_id=section_id, direction=direction)
    except section_structure_service.SectionStructureError as exc:
        raise R4MutationError(exc.code) from exc


def _dispatch_mutation(*, store, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    """The one explicit, server-owned allowlist — no getattr-on-user-input,
    no globals(), no dynamic import, no eval. ``store`` is accepted (not
    used by every mutation type) to keep the dispatcher's signature stable
    for future allowlisted mutation types that need it."""
    mutation_type = mutation.get("type")
    if mutation_type == "section.update_settings":
        _apply_section_update_settings(store=store, draft=draft, mutation=mutation)
        return
    if mutation_type == "section.add":
        _apply_section_add(draft=draft, mutation=mutation)
        return
    if mutation_type == "section.remove":
        _apply_section_remove(draft=draft, mutation=mutation)
        return
    if mutation_type == "section.duplicate":
        _apply_section_duplicate(draft=draft, mutation=mutation)
        return
    if mutation_type == "section.move":
        _apply_section_move(draft=draft, mutation=mutation)
        return
    raise R4MutationError("unknown_mutation_type")


@transaction.atomic
def apply_mutation(*, store, actor, base_revision: int, mutation: dict) -> int:
    if not isinstance(mutation, dict):
        raise R4MutationError("invalid_mutation")

    layout = StorefrontLayout.objects.select_for_update().get(store=store)

    if layout.draft_version_id is None:
        raise R4MutationError("no_active_draft")

    try:
        draft = StorefrontLayoutVersion.objects.select_for_update().get(
            pk=layout.draft_version_id,
            layout=layout,
            status=StorefrontLayoutVersion.Status.DRAFT,
        )
    except StorefrontLayoutVersion.DoesNotExist:
        raise R4MutationError("no_active_draft") from None

    if draft.edit_revision != base_revision:
        raise R4StaleRevision(draft.edit_revision)

    before_state = edit_history_service.snapshot_draft(draft)

    _dispatch_mutation(store=store, draft=draft, mutation=mutation)

    draft.edit_revision += 1
    draft.save(update_fields=["edit_revision"])

    edit_history_service.record_change(
        draft=draft,
        actor=actor,
        action_label=_history_label(mutation),
        before_state=before_state,
    )

    return draft.edit_revision
