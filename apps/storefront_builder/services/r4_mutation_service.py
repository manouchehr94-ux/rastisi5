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

from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.services import edit_history_service
from apps.storefront_builder.settings_schema import SettingsSchemaError, clean_section_schema_patch


class R4MutationError(ValueError):
    pass


class R4StaleRevision(R4MutationError):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("stale_revision")


_MUTATION_HISTORY_LABELS = {
    "section.update_settings": "ویرایش تنظیمات بخش",
}


def _history_label(mutation: dict) -> str:
    return _MUTATION_HISTORY_LABELS.get(mutation.get("type"), "ویرایش R4")


def _is_strict_int(value: object) -> bool:
    return type(value) is int


def _apply_section_update_settings(*, draft: StorefrontLayoutVersion, mutation: dict) -> None:
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

    try:
        cleaned = clean_section_schema_patch(definition, patch, section.settings or {})
    except SettingsSchemaError as exc:
        raise R4MutationError(str(exc)) from exc

    section.settings = cleaned
    section.save(update_fields=["settings"])


def _dispatch_mutation(*, store, draft: StorefrontLayoutVersion, mutation: dict) -> None:
    """The one explicit, server-owned allowlist — no getattr-on-user-input,
    no globals(), no dynamic import, no eval. ``store`` is accepted (not
    used by this Phase 0's single mutation type) to keep the dispatcher's
    signature stable for future allowlisted mutation types that need it."""
    mutation_type = mutation.get("type")
    if mutation_type == "section.update_settings":
        _apply_section_update_settings(draft=draft, mutation=mutation)
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
