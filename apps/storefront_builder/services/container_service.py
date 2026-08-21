"""Container/Cell layout foundation for Storefront Builder.

The legacy builder grouped adjacent sections with ``row_key``/``row_span``.
That makes content itself responsible for layout, which is awkward for a real
site builder: a merchant cannot create an empty two-column layout first and put
content into each slot later.

This service introduces a separate placement layer:

    StorefrontPage -> StorefrontContainer -> StorefrontCell -> StorefrontSection

``StorefrontSection`` remains the content object (registry/settings/media and
page scoping stay intact).  A Cell may be empty.  The Cell ``span`` values are
the actual desktop layout source of truth; ``layout_key`` is only a preset hint
for the editor.

During the migration window ``row_key``/``row_span`` remain available for
backward compatibility.  Helpers in this module can mirror legacy rows into the
new structure without changing public rendering yet.

Phase 2B — multi-block Cell runtime foundation
-----------------------------------------------
Phase 2A added two transitional, purely-additive fields to ``StorefrontSection``:
``cell`` (nullable FK, ``related_name="blocks"``) and ``cell_order`` (int,
meaningful only when ``cell`` is set).  ``StorefrontCell.section`` (the
original OneToOne) is deliberately **kept unchanged** during Phase 2B — it
remains the only relationship every pre-Phase-2B call site reads/writes.

This module now also owns the single authoritative read path for "what is in
this Cell" (``get_cell_blocks``) and the mutating multi-block operations (add/
remove/move/reorder) a future editor UI will call.  The read path's precedence
rule is intentionally simple and matches the owner's explicit spec: if the new
``cell`` relationship has *any* blocks, use it exclusively; only fall back to
the legacy ``section`` OneToOne when the new relationship is completely empty
for that Cell.  A Section that both relationships happen to reference (the
normal state left behind by the Phase 2A migration backfill) is therefore
always returned exactly once, never twice — see ``get_cell_blocks`` below for
the precise rule and ``_clear_stale_legacy_pointer`` for how every mutating
operation keeps the two relationships from ever describing two *different*
placements for the same Section (which would otherwise resurrect a stale
legacy pointer into a duplicate render after a block moves away).

Nothing in this phase changes ``place_section`` (kept as-is, per the owner's
explicit instruction, as the compatibility operation every pre-existing
single-block call site — views.py, tests — continues to use unmodified) or
removes/deprecates the legacy OneToOne.  Phase 2C will decide if/when that
happens.
"""

from __future__ import annotations

from copy import deepcopy

from django.db import transaction

from ..models import StorefrontCell, StorefrontContainer, StorefrontSection

GRID_UNITS = 12
MAX_CELLS = 4

LAYOUT_PRESETS: dict[str, tuple[int, ...]] = {
    "single": (12,),
    "half": (6, 6),
    "quarter_left": (3, 9),
    "quarter_right": (9, 3),
    "third_left": (4, 8),
    "third_right": (8, 4),
    "thirds": (4, 4, 4),
    "quarters": (3, 3, 3, 3),
}

CONTAINER_SETTINGS_DEFAULTS = {
    "gap": 14,
    "mobile_mode": "stack",   # stack | same
    "content_width": "standard",  # standard | full
    # Independent content blocks should keep their natural height.  The old
    # ``stretch`` default made a short Slider Cell look as tall as a long
    # product grid beside it, which visually looked like broken layout.
    "vertical_align": "start",  # start | center | end
    # ``natural`` keeps each Cell at its own content height. ``equal`` is an
    # explicit composition tool for deliberately matched siblings such as a
    # Hero + compact side offer or two same-kind product panels.
    "height_mode": "natural",  # natural | equal
    # Optional surface owned by the layout itself.  Section backgrounds remain
    # independent, so a merchant can color either one content rail or a whole
    # multi-cell composition.
    "background_mode": "transparent",  # transparent | color | pattern
    "background_color": "",
    "background_pattern": "",
}


class ContainerLayoutError(ValueError):
    """Invalid Container/Cell assignment; safe to show to the merchant."""


def layout_key_for_spans(spans) -> str:
    spans = tuple(int(value) for value in spans)
    for key, preset in LAYOUT_PRESETS.items():
        if spans == preset:
            return key
    return "custom"


def effective_container_settings(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    cleaned = dict(CONTAINER_SETTINGS_DEFAULTS)

    try:
        gap = int(raw.get("gap", cleaned["gap"]))
    except (TypeError, ValueError):
        gap = cleaned["gap"]
    cleaned["gap"] = max(0, min(64, gap))

    mobile_mode = raw.get("mobile_mode", cleaned["mobile_mode"])
    if mobile_mode not in {"stack", "same"}:
        mobile_mode = cleaned["mobile_mode"]
    cleaned["mobile_mode"] = mobile_mode

    content_width = raw.get("content_width", cleaned["content_width"])
    if content_width not in {"standard", "full"}:
        content_width = cleaned["content_width"]
    cleaned["content_width"] = content_width

    vertical_align = raw.get("vertical_align", cleaned["vertical_align"])
    # Phase 3.2: old Container rows were persisted with ``stretch`` as their
    # implicit default.  Treat that legacy value as the safer natural-height
    # top alignment without requiring a data migration.
    if vertical_align == "stretch":
        vertical_align = "start"
    if vertical_align not in {"start", "center", "end"}:
        vertical_align = cleaned["vertical_align"]
    cleaned["vertical_align"] = vertical_align

    height_mode = raw.get("height_mode", cleaned["height_mode"])
    if height_mode not in {"natural", "equal"}:
        height_mode = cleaned["height_mode"]
    cleaned["height_mode"] = height_mode

    background_mode = raw.get("background_mode", cleaned["background_mode"])
    if background_mode not in {"transparent", "color", "pattern"}:
        background_mode = cleaned["background_mode"]

    background_color = str(raw.get("background_color", cleaned["background_color"]) or "").strip()
    if background_mode in {"color", "pattern"}:
        if background_color:
            from django.core.exceptions import ValidationError as DjangoValidationError
            from apps.core.models import validate_hex_color
            try:
                validate_hex_color(background_color)
            except DjangoValidationError:
                background_mode = "transparent"
                background_color = ""
        elif background_mode == "color":
            background_mode = "transparent"

    background_pattern = str(raw.get("background_pattern", cleaned["background_pattern"]) or "").strip()
    if background_mode == "pattern":
        from ..section_registry import PATTERN_REGISTRY
        if background_pattern not in PATTERN_REGISTRY:
            background_mode = "transparent"
            background_pattern = ""

    cleaned["background_mode"] = background_mode
    cleaned["background_color"] = background_color
    cleaned["background_pattern"] = background_pattern
    return cleaned


def validate_container(container: StorefrontContainer, cells=None) -> None:
    cells = list(cells if cells is not None else container.cells.select_related("section").order_by("order", "id"))
    if not 1 <= len(cells) <= MAX_CELLS:
        raise ContainerLayoutError(
            f"هر چیدمان باید بین ۱ تا {MAX_CELLS} خانه داشته باشد"
        )

    total = 0
    seen_orders = set()
    for cell in cells:
        if cell.order in seen_orders:
            raise ContainerLayoutError("ترتیب خانه‌های یک چیدمان تکراری است")
        seen_orders.add(cell.order)
        if not 1 <= int(cell.span) <= GRID_UNITS:
            raise ContainerLayoutError("عرض هر خانه باید بین ۱ تا ۱۲ باشد")
        total += int(cell.span)
        if cell.section_id and cell.section.page_id != container.page_id:
            raise ContainerLayoutError("محتوای یک خانه باید متعلق به همان صفحه باشد")
        # Phase 2B: the new multi-block FK's Blocks must obey the exact same
        # page-scoping invariant as the legacy single-block OneToOne above —
        # a Block placed via ``add_block``/``move_block`` can never belong to
        # a different Page than its Cell's Container.
        for block in cell.blocks.all():
            if block.page_id != container.page_id:
                raise ContainerLayoutError("محتوای یک خانه باید متعلق به همان صفحه باشد")
    if total != GRID_UNITS:
        raise ContainerLayoutError(
            f"مجموع عرض خانه‌های چیدمان باید دقیقاً {GRID_UNITS} باشد — مقدار فعلی: {total}"
        )


def validate_page_containers(page) -> None:
    placed_sections = set()
    container_orders = set()
    for container in page.containers.order_by("order", "id").prefetch_related("cells__section", "cells__blocks"):
        if container.order in container_orders:
            raise ContainerLayoutError("ترتیب Containerهای صفحه تکراری است")
        container_orders.add(container.order)
        cells = list(container.cells.all().order_by("order", "id"))
        validate_container(container, cells)
        for cell in cells:
            cell_section_ids = {block.pk for block in cell.blocks.all()} or (
                {cell.section_id} if cell.section_id else set()
            )
            overlap = cell_section_ids & placed_sections
            if overlap:
                raise ContainerLayoutError("یک بخش نمی‌تواند هم‌زمان در دو خانه باشد")
            placed_sections |= cell_section_ids


def _legacy_runs(page):
    """Yield legacy row runs exactly in visual order, without mutating them."""
    ordered = list(page.sections.order_by("order", "id"))
    i = 0
    while i < len(ordered):
        first = ordered[i]
        key = first.row_key or ""
        if not key:
            yield [first]
            i += 1
            continue
        run = [first]
        i += 1
        while i < len(ordered) and (ordered[i].row_key or "") == key:
            run.append(ordered[i])
            i += 1
        yield run


@transaction.atomic
def rebuild_page_from_legacy_rows(page) -> None:
    """Mirror the current legacy row metadata into Container/Cell rows.

    This is intentionally a transition helper.  It makes no public-rendering
    decision and does not edit ``row_key``/``row_span``.  Existing Container
    rows are replaced so the shadow model exactly matches the old builder state.
    """
    page.containers.all().delete()
    container_order = 0
    for run in _legacy_runs(page):
        spans = [section.row_span if section.row_key else 12 for section in run]
        container = StorefrontContainer.objects.create(
            page=page,
            order=container_order,
            layout_key=layout_key_for_spans(spans),
            settings=dict(CONTAINER_SETTINGS_DEFAULTS),
        )
        StorefrontCell.objects.bulk_create([
            StorefrontCell(
                container=container,
                order=index,
                span=span,
                section=section,
            )
            for index, (section, span) in enumerate(zip(run, spans))
        ])
        container_order += 1


@transaction.atomic
def ensure_page_containers(page) -> None:
    """Ensure a page has placements without destroying an existing new layout.

    If there are no containers at all, legacy rows are mirrored.  If containers
    already exist, only sections that currently have no Cell are appended in
    new single-column containers.  Empty Cells are preserved.
    """
    if not page.containers.exists():
        if page.sections.exists():
            rebuild_page_from_legacy_rows(page)
        return

    placed_ids = set(
        StorefrontCell.objects.filter(
            container__page=page,
            section__isnull=False,
        ).values_list("section_id", flat=True)
    )
    # Phase 2B: a Section placed via the new multi-block FK (``add_block``/
    # ``move_block``) is just as "placed" as one via the legacy OneToOne —
    # the publish invariant (§13) requires it counts as correctly placed too,
    # so it must never be treated as orphaned/unplaced and wrapped into a
    # brand-new single-column Container here.
    placed_ids |= set(
        StorefrontSection.objects.filter(page=page, cell__isnull=False).values_list("pk", flat=True)
    )
    last_order = page.containers.order_by("-order").values_list("order", flat=True).first()
    next_order = (last_order + 1) if last_order is not None else 0
    for section in page.sections.exclude(pk__in=placed_ids).order_by("order", "id"):
        container = StorefrontContainer.objects.create(
            page=page,
            order=next_order,
            layout_key="single",
            settings=dict(CONTAINER_SETTINGS_DEFAULTS),
        )
        StorefrontCell.objects.create(container=container, order=0, span=12, section=section)
        next_order += 1


def ensure_version_containers(version) -> None:
    for page in version.pages.all():
        ensure_page_containers(page)


@transaction.atomic
def create_empty_container(page, layout_key: str = "single", *, order: int | None = None, settings=None):
    spans = LAYOUT_PRESETS.get(layout_key)
    if spans is None:
        raise ContainerLayoutError("چینش انتخاب‌شده معتبر نیست")

    if order is None:
        last = page.containers.order_by("-order").first()
        order = (last.order + 1) if last else 0

    container = StorefrontContainer.objects.create(
        page=page,
        order=order,
        layout_key=layout_key,
        settings=effective_container_settings(settings),
    )
    StorefrontCell.objects.bulk_create([
        StorefrontCell(container=container, order=index, span=span)
        for index, span in enumerate(spans)
    ])
    return container


@transaction.atomic
def place_section(cell: StorefrontCell, section: StorefrontSection) -> StorefrontCell:
    """Place ``section`` as the sole occupant of ``cell`` — the pre-Phase-2B,
    single-block compatibility operation every existing Builder write path
    (views.py's ``storefront_cell_add_section``, and every pre-Phase-2B test)
    calls unmodified.

    Phase 2B correction (real-environment verification found the original
    Phase 2B design left this function's contract incomplete): this function
    keeps writing the legacy ``StorefrontCell.section`` OneToOne exactly as
    before — that write, and this function's externally-visible single-
    occupant behaviour/error conditions, are UNCHANGED. What changes is that
    it now also keeps the new multi-block FK synchronized with the same
    outcome, so ``get_cell_blocks`` (the single authoritative read path) can
    never disagree with what this call just established:

    - Any OTHER Section currently attached to ``cell`` via the new FK (a
      leftover multi-block Block that no longer reflects reality once this
      call makes ``section`` the Cell's sole occupant) is detached — never
      deleted, only unlinked from this Cell — exactly like ``remove_block``
      never deletes a Section it detaches.
    - ``section`` itself becomes this Cell's sole new-FK Block
      (``cell_order=0``), regardless of where it previously was attached
      via the new FK (nowhere, this same Cell, or a different Cell) — if it
      was attached elsewhere, that other Cell's remaining Blocks are
      compacted (0..N-1, no gaps), the same guarantee ``remove_block``/
      ``move_block`` already make.

    This does not change ``place_section``'s single-occupant contract or its
    two existing rejection conditions (cross-page; Cell already holds a
    *different* Section) — it only makes sure that contract is honoured by
    BOTH relationships at once, not just the legacy one, since the current
    Builder UI still calls this function directly and its result must be
    trustworthy through the new read path too.
    """
    cell = StorefrontCell.objects.select_for_update().select_related("container").get(pk=cell.pk)
    if cell.container.page_id != section.page_id:
        raise ContainerLayoutError("این محتوا متعلق به صفحه دیگری است")
    if cell.section_id and cell.section_id != section.pk:
        raise ContainerLayoutError("این خانه از قبل محتوا دارد")

    # OneToOne prevents two cells from owning the same section.  Explicitly
    # clear the old placement to make a future drag-between-cells operation
    # atomic and predictable.
    StorefrontCell.objects.filter(section=section).exclude(pk=cell.pk).update(section=None)
    cell.section = section
    cell.save(update_fields=["section", "updated_at"])

    old_cell_id = section.cell_id
    stale_siblings = list(
        StorefrontSection.objects.select_for_update()
        .filter(cell_id=cell.pk).exclude(pk=section.pk)
    )
    for row in stale_siblings:
        row.cell = None
        row.cell_order = 0
    if stale_siblings:
        StorefrontSection.objects.bulk_update(stale_siblings, ["cell", "cell_order"])

    section.cell = cell
    section.cell_order = 0
    section.save(update_fields=["cell", "cell_order", "updated_at"])

    if old_cell_id is not None and old_cell_id != cell.pk:
        remaining = list(
            StorefrontSection.objects.select_for_update()
            .filter(cell_id=old_cell_id)
            .order_by("cell_order", "id")
        )
        for index, row in enumerate(remaining):
            row.cell_order = index
        _persist_cell_order(remaining)

    return cell


def get_cell_blocks(cell: StorefrontCell) -> list[StorefrontSection]:
    """Authoritative read path: the ordered list of Blocks placed in ``cell``.

    Precedence rule (Phase 2B, matches the owner's explicit spec): if the new
    ``cell.blocks`` relationship has *any* rows, they are the whole answer —
    ordered by ``cell_order`` then ``id`` for a deterministic tie-break
    (``StorefrontSection.Meta.ordering`` is ``["order", "id"]``, which is the
    unrelated *page-level* ordering — never used here). Only when
    ``cell.blocks`` is completely empty for this Cell does this function fall
    back to the legacy ``cell.section`` OneToOne, so a Cell that has never
    been touched by any Phase 2B-aware code (i.e. every Cell today, until a
    caller starts using ``add_block``/``move_block`` below) keeps behaving
    exactly as it always has.

    This single rule is what guarantees a Section is never rendered twice
    even though, immediately after the Phase 2A migration backfill, both
    relationships legitimately point at the same Section — that state is
    exactly "``cell.blocks`` has one row", so the legacy branch is never
    reached for it.
    """
    blocks = list(cell.blocks.order_by("cell_order", "id"))
    if blocks:
        return blocks
    # Fallback: read the legacy single-block placement FRESH from the
    # database rather than trusting `cell.section_id`/`cell.section` on
    # whatever Python instance the caller happened to pass in.
    #
    # `cell.blocks.order_by(...)` above is always a live query regardless of
    # caller staleness (Django never serves `.order_by()` on a related
    # manager from a prefetch cache — only a bare `.all()` can do that), but
    # a plain FK attribute like `cell.section_id` is exactly whatever value
    # was loaded onto THIS specific instance when it was fetched. Several
    # existing call sites — most notably `place_section` — intentionally
    # re-fetch and mutate their OWN internal `StorefrontCell` instance
    # rather than the caller's (`cell = StorefrontCell.objects...get(...)`
    # shadows the parameter), so a caller that keeps using the object it
    # already had (exactly what today's real Builder call sites do) can be
    # legitimately stale immediately after such a call returns. Verified
    # against a real Django run: this was the exact cause of
    # ``get_cell_blocks`` returning ``[]`` right after
    # ``place_section(cell, section)`` in the caller's own test.
    #
    # Since this is meant to be THE single authoritative composition-read
    # entry point, it must never answer wrong merely because of which
    # specific Python object was passed in — one extra, cheap, PK-scoped
    # query (only ever executed in this fallback branch, i.e. only for a
    # Cell that has no new-FK Blocks yet — the overwhelming majority of
    # Cells today) is a fully justified, small cost for that guarantee,
    # and is far safer than requiring every caller to remember to call
    # ``refresh_from_db()`` first.
    fresh_cell = StorefrontCell.objects.filter(pk=cell.pk).select_related("section").first()
    if fresh_cell is not None and fresh_cell.section_id:
        return [fresh_cell.section]
    return []


# Any two-phase temporary `cell_order` value must be larger than any real
# value the application ever assigns (single-digit-to-low-hundreds per Cell
# in practice) while staying comfortably inside `PositiveIntegerField`'s
# range (0..2_147_483_647). Offsetting by each row's own primary key keeps
# the temporary values trivially unique across a batch without an extra
# query.
_CELL_ORDER_TEMP_OFFSET = 1_000_000_000


def _persist_cell_order(rows: list[StorefrontSection]) -> None:
    """Collision-safe write of ``cell_order`` for every row in ``rows`` (all
    belonging to the same Cell), where each row's ``.cell_order`` attribute
    has ALREADY been set in memory to its desired FINAL value by the caller.

    Why this exists (root-caused against a real Django+SQLite run, not
    assumed): ``StorefrontSection`` carries a database-level conditional
    ``UniqueConstraint(fields=["cell", "cell_order"], condition=Q(cell__isnull=False))``
    from Phase 2A — correct, and never removed by this fix. A naive single
    ``bulk_update`` that writes several rows' FINAL values directly (e.g.
    swapping two rows' positions, or shifting several rows up by one to make
    room for an insert) can violate that constraint *mid-statement*: neither
    SQLite nor PostgreSQL guarantees a multi-row UPDATE applies every row
    "as if simultaneously" — one row being set to a new value can transiently
    collide with *another* row's still-old value before that other row's own
    update is applied within the very same statement. This is exactly the
    ``IntegrityError`` a real Django+SQLite test run reproduced for every
    reorder/shift/compaction path in this module (``reorder_block``,
    ``reorder_blocks_in_cell``, ``add_block``'s insert-shift, ``remove_block``'s
    compaction).

    The fix is the standard collision-free reorder technique: write every
    participating row into a disjoint SCRATCH range first (Phase 1), then —
    only once every row's *persisted* value is safely outside the small real
    ``cell_order`` range — write the real final values (Phase 2). Because the
    scratch range and the real range never overlap, no row's new value can
    ever equal another row's not-yet-updated value in *either* phase,
    regardless of what order the database applies the rows in. Two plain
    ``bulk_update`` calls (two separate SQL statements, run strictly
    sequentially inside the caller's ``transaction.atomic()``) are enough;
    this works identically on SQLite and PostgreSQL because it never depends
    on intra-statement row-processing order at all.

    Callers pass the FULL set of rows whose ``cell_order`` may need to
    change for a given operation (not just the subset that actually differs
    from its old value) — writing a row's already-correct value again is a
    harmless no-op, and always operating on the full set keeps this one
    helper trivially correct for every call site rather than requiring each
    call site to reason about partial-update edge cases independently.
    """
    if not rows:
        return
    final_orders = [row.cell_order for row in rows]
    for row in rows:
        # Every row's primary key is already unique, so offsetting by ``pk``
        # needs no extra query to guarantee distinct temporary values.
        row.cell_order = _CELL_ORDER_TEMP_OFFSET + row.pk
    StorefrontSection.objects.bulk_update(rows, ["cell_order"])
    for row, order in zip(rows, final_orders):
        row.cell_order = order
    StorefrontSection.objects.bulk_update(rows, ["cell_order"])


def _clear_stale_legacy_pointer(section: StorefrontSection, *, keep_cell_id: int | None) -> None:
    """Prevent a Section from being reachable through *two different*
    placements at once (new FK vs. legacy OneToOne) after a Phase 2B
    mutation moves/removes it.

    Immediately after the Phase 2A backfill, and for any Section a
    Phase-2B-unaware call site has ever placed via ``place_section``, a
    Section's legacy ``placement_cell`` (``StorefrontCell.section``, reverse
    OneToOne) and its new ``cell`` FK point at the very same Cell — this is
    the intended, harmless steady state ``get_cell_blocks`` relies on (one
    Cell, one set of blocks, no duplication).  But once a Phase 2B operation
    moves that Section to a *different* Cell (or detaches it entirely) via
    the new FK, the stale legacy OneToOne would otherwise keep pointing at
    the Cell the Section just left — which would make that now-vacated Cell's
    ``get_cell_blocks`` fall back to a Section that no longer belongs there
    once (in a future step) the new relationship's row for it disappears too,
    or, more subtly, would let *that original Cell* still "see" the Section
    via the legacy branch on a request that races the transaction boundary.
    Clearing the stale pointer whenever the new FK changes a Section's Cell
    keeps the two relationships from ever describing two different
    placements for the same Section at once — never left in a state where
    both are simultaneously true but disagree.

    ``keep_cell_id=None`` means "detach the Section from Cell placement
    entirely" (used by ``remove_block``); any other value means "the legacy
    pointer is only allowed to keep pointing at *this* Cell going forward".
    """
    try:
        legacy_cell = section.placement_cell
    except StorefrontCell.DoesNotExist:
        legacy_cell = None
    if legacy_cell is not None and legacy_cell.pk != keep_cell_id:
        legacy_cell.section = None
        legacy_cell.save(update_fields=["section", "updated_at"])


@transaction.atomic
def add_block(cell: StorefrontCell, section: StorefrontSection, *, at_index: int | None = None) -> StorefrontSection:
    """Place ``section`` into ``cell`` as one Block among (possibly several)
    others already there — the multi-block-capable sibling of
    ``place_section``, which stays untouched as the single-block compatibility
    operation.

    Same tenant/page/lock invariants as ``place_section``: the Section must
    belong to the same Page as the Cell's Container, and a locked Container
    is rejected — but, unlike ``place_section``, an already-occupied Cell is
    not itself an error; that is the entire point of this operation.

    ``at_index`` controls the insertion position among the Cell's *existing*
    blocks (``None``/omitted appends at the end — the common "add one more
    block" case); every following existing block's ``cell_order`` shifts up
    by one to make room, so relative order is always preserved and no two
    blocks in one Cell ever end up sharing a ``cell_order`` value (the exact
    invariant ``StorefrontSection``'s conditional ``UniqueConstraint`` on
    ``(cell, cell_order)`` from Phase 2A enforces at the database level).

    If ``section`` is the Cell's own pre-existing legacy single block (i.e.
    ``cell.section_id == section.pk``, the normal post-Phase-2A-backfill
    steady state), this call *adopts* that same content into the new FK at
    position 0 rather than double-placing it — so calling ``add_block`` on a
    freshly-migrated single-content Cell with its own current content is a
    safe, idempotent way to "start managing this Cell as multi-block", not a
    duplicate.
    """
    cell = StorefrontCell.objects.select_for_update().select_related("container").get(pk=cell.pk)
    if cell.container.page_id != section.page_id:
        raise ContainerLayoutError("این محتوا متعلق به صفحه دیگری است")
    if cell.container.is_locked:
        raise ContainerLayoutError("این چیدمان قفل است — ابتدا قفل آن را باز کنید")

    existing = list(
        StorefrontSection.objects.select_for_update()
        .filter(cell_id=cell.pk)
        .order_by("cell_order", "id")
    )
    if section.pk in {row.pk for row in existing}:
        # Already one of this Cell's Blocks (new FK) — nothing to add, and
        # never treated as an error: repeating an add is a safe no-op.
        return section

    if not existing and cell.section_id == section.pk:
        # Adopt the Cell's own legacy single block into the new FK instead of
        # creating a second placement for the same Section.
        section.cell = cell
        section.cell_order = 0
        section.save(update_fields=["cell", "cell_order", "updated_at"])
        return section

    if existing:
        insert_at = len(existing) if at_index is None else max(0, min(at_index, len(existing)))
        for index, row in enumerate(existing):
            row.cell_order = index + 1 if index >= insert_at else index
        _persist_cell_order(existing)
        new_order = insert_at
    else:
        new_order = 0

    _clear_stale_legacy_pointer(section, keep_cell_id=cell.pk)
    section.cell = cell
    section.cell_order = new_order
    section.save(update_fields=["cell", "cell_order", "updated_at"])
    return section


@transaction.atomic
def remove_block(section: StorefrontSection) -> None:
    """Detach ``section`` from whichever Cell currently holds it as a Block —
    the multi-block sibling of ``storefront_cell_clear``'s legacy behaviour,
    except this never deletes the Section itself (the legacy view-level
    ``cell_clear`` endpoint intentionally does delete the Section — see the
    module docstring's Phase 2B note and ``views.storefront_cell_clear``,
    which is left completely unmodified in this phase).  Removing one Block
    must never destroy the Cell or Container, and must never destroy any
    *other* Block still in the same Cell — only this one Section's placement
    is cleared, and the remaining Blocks' ``cell_order`` values are
    compacted (0..N-1, no gaps) so a future insert-at-index stays predictable.
    """
    has_new_placement = section.cell_id is not None
    has_legacy_placement = _has_legacy_placement(section)
    if not has_new_placement and not has_legacy_placement:
        return

    cell_id = section.cell_id
    _clear_stale_legacy_pointer(section, keep_cell_id=None)
    if has_new_placement:
        section.cell = None
        section.cell_order = 0
        section.save(update_fields=["cell", "cell_order", "updated_at"])

    if cell_id is not None:
        remaining = list(
            StorefrontSection.objects.select_for_update()
            .filter(cell_id=cell_id)
            .order_by("cell_order", "id")
        )
        for index, row in enumerate(remaining):
            row.cell_order = index
        _persist_cell_order(remaining)


def _has_legacy_placement(section: StorefrontSection) -> bool:
    try:
        return section.placement_cell is not None
    except StorefrontCell.DoesNotExist:
        return False


@transaction.atomic
def move_block(section: StorefrontSection, target_cell: StorefrontCell, *, at_index: int | None = None) -> StorefrontSection:
    """Move ``section`` from wherever it currently is into ``target_cell`` —
    Cell A -> Cell B, preserving the Section's identity (``stable_id``/PK)
    and re-homing it to the end of ``target_cell``'s Blocks (or a specific
    ``at_index``) while compacting the source Cell's remaining Blocks'
    ``cell_order`` values, exactly like ``remove_block``.

    Same tenant/page/lock invariants as ``add_block``: ``target_cell`` must
    belong to the same Page as ``section``, and its Container must not be
    locked.  Moving *within* the same Cell (``target_cell.pk == section.cell_id``)
    is accepted as a same-Cell reorder-to-position rather than an error.
    """
    target_cell = StorefrontCell.objects.select_for_update().select_related("container").get(pk=target_cell.pk)
    if target_cell.container.page_id != section.page_id:
        raise ContainerLayoutError("این محتوا متعلق به صفحه دیگری است")
    if target_cell.container.is_locked:
        raise ContainerLayoutError("این چیدمان قفل است — ابتدا قفل آن را باز کنید")

    source_cell_id = section.cell_id
    if source_cell_id == target_cell.pk:
        # Same-Cell move is just a reorder to a new position.
        return reorder_block(section, at_index=at_index)

    remove_block(section)
    return add_block(target_cell, section, at_index=at_index)


@transaction.atomic
def reorder_block(section: StorefrontSection, *, at_index: int | None = None) -> StorefrontSection:
    """Move ``section`` to position ``at_index`` among the *other* Blocks
    already in its own current Cell — the same-Cell special case of
    ``reorder_blocks_in_cell`` below, expressed in terms of a single moved
    Block rather than a full target ordering (a convenient primitive for a
    drag-and-drop editor gesture that only knows "this Block moved to this
    position", not the whole resulting list). ``at_index=None`` leaves the
    Block at its own current position (a safe no-op — used by ``move_block``
    when a same-Cell "move" was requested without a specific target index).
    """
    if section.cell_id is None:
        raise ContainerLayoutError("این محتوا داخل هیچ خانه‌ای نیست")
    if at_index is None:
        return section
    cell_id = section.cell_id
    siblings = list(
        StorefrontSection.objects.select_for_update()
        .filter(cell_id=cell_id)
        .exclude(pk=section.pk)
        .order_by("cell_order", "id")
    )
    insert_at = max(0, min(at_index, len(siblings)))
    siblings.insert(insert_at, section)
    for index, row in enumerate(siblings):
        row.cell_order = index
    _persist_cell_order(siblings)
    return section


@transaction.atomic
def reorder_blocks_in_cell(cell: StorefrontCell, section_ids_in_order: list[int]) -> None:
    """Rewrite the ``cell_order`` of every Block currently in ``cell`` to
    match ``section_ids_in_order`` exactly — the batch/"drop this whole new
    order" primitive (e.g. after a full drag-and-drop reorder gesture that
    already knows the complete resulting sequence), as opposed to
    ``reorder_block``'s single-item "moved to position N" primitive above.

    Rejects (raises ``ContainerLayoutError``, safe to show to the merchant)
    unless ``section_ids_in_order`` is *exactly* the same set of ids
    currently in the Cell — no partial reorder, no silently dropping or
    smuggling in a Section that doesn't already belong to this Cell, no
    duplicate ids. This mirrors the existing ``storefront_section_reorder``
    view's own "reject the whole operation on any mismatch, all-or-nothing"
    convention (see ``views.py``) rather than inventing a new one.
    """
    cell = StorefrontCell.objects.select_for_update().select_related("container").get(pk=cell.pk)
    current = list(
        StorefrontSection.objects.select_for_update()
        .filter(cell_id=cell.pk)
        .order_by("cell_order", "id")
    )
    current_by_id = {row.pk: row for row in current}
    if len(section_ids_in_order) != len(set(section_ids_in_order)):
        raise ContainerLayoutError("شناسه‌های تکراری در ترتیب جدید مجاز نیست")
    if set(section_ids_in_order) != set(current_by_id):
        raise ContainerLayoutError("ترتیب جدید باید دقیقاً همان بلاک‌های موجود در این خانه باشد")

    for index, section_id in enumerate(section_ids_in_order):
        current_by_id[section_id].cell_order = index
    # All participating rows are passed through the collision-safe helper,
    # not only the ones whose value actually changes — re-writing an
    # already-correct value is a harmless no-op, and this keeps the helper
    # trivially correct for every caller without needing per-call-site
    # partial-update reasoning (see ``_persist_cell_order`` docstring).
    _persist_cell_order(current)


@transaction.atomic
def clone_page_containers(source_page, target_page, target_sections_by_stable_id: dict) -> None:
    """Clone layout placement while preserving logical Container/Cell IDs.

    Phase 2B: also clones the new multi-block FK placement (``cell``/
    ``cell_order``) for every Block a source Cell holds, in exactly the same
    ``cell_order`` sequence, matched onto the already-cloned target Sections
    by ``stable_id`` — the same identity-preservation mechanism the legacy
    single-block ``section=`` line above already uses (``target_sections_by_stable_id``
    is the caller's ``cloned_by_stable_id`` map built from freshly-cloned
    target Sections, keyed by the *shared* ``stable_id`` both the source and
    target Section rows carry). Stable IDs are never invented or reassigned
    here — only looked up.
    """
    target_page.containers.all().delete()
    source_containers = list(
        source_page.containers.prefetch_related("cells__section", "cells__blocks").order_by("order", "id")
    )
    if not source_containers:
        rebuild_page_from_legacy_rows(target_page)
        return

    for source_container in source_containers:
        target_container = StorefrontContainer.objects.create(
            page=target_page,
            order=source_container.order,
            stable_id=source_container.stable_id,
            layout_key=source_container.layout_key,
            settings=deepcopy(source_container.settings or {}),
            is_locked=source_container.is_locked,
        )
        cells = []
        source_cells = list(source_container.cells.all().order_by("order", "id"))
        for source_cell in source_cells:
            target_section = None
            if source_cell.section_id:
                target_section = target_sections_by_stable_id.get(source_cell.section.stable_id)
            cells.append(StorefrontCell(
                container=target_container,
                order=source_cell.order,
                stable_id=source_cell.stable_id,
                span=source_cell.span,
                section=target_section,
                settings=deepcopy(source_cell.settings or {}),
            ))
        StorefrontCell.objects.bulk_create(cells)

        # Second pass (mirrors ``layout_service._clone_version_content``'s own
        # re-fetch-by-stable_id pattern): bulk_create above does not
        # reliably populate PKs on every backend, so the just-created target
        # Cells are re-fetched by ``stable_id`` before wiring up the new
        # multi-block FK on the matching target Sections.
        target_cells_by_stable_id = {
            cell.stable_id: cell for cell in target_container.cells.all()
        }
        blocks_to_update = []
        for source_cell in source_cells:
            target_cell = target_cells_by_stable_id.get(source_cell.stable_id)
            if target_cell is None:
                continue
            for source_block in source_cell.blocks.order_by("cell_order", "id"):
                target_block = target_sections_by_stable_id.get(source_block.stable_id)
                if target_block is None:
                    continue
                target_block.cell_id = target_cell.pk
                target_block.cell_order = source_block.cell_order
                blocks_to_update.append(target_block)
        if blocks_to_update:
            StorefrontSection.objects.bulk_update(blocks_to_update, ["cell", "cell_order"])

@transaction.atomic
def change_container_layout(container: StorefrontContainer, layout_key: str) -> StorefrontContainer:
    """Change one Container preset without treating content as the layout.

    Existing leading Cells keep their content. Growing adds real empty Cells.
    Shrinking is allowed only when every Cell that would disappear is empty, so
    content is never silently deleted or moved. This is the core merchant UX:
    choose the shape first, then fill the empty slots.
    """
    spans = LAYOUT_PRESETS.get(layout_key)
    if spans is None:
        raise ContainerLayoutError("چینش انتخاب‌شده معتبر نیست")

    container = StorefrontContainer.objects.select_for_update().get(pk=container.pk)
    if container.is_locked:
        raise ContainerLayoutError("این چیدمان قفل است — ابتدا قفل آن را باز کنید")

    cells = list(
        StorefrontCell.objects.select_for_update()
        .filter(container=container)
        .select_related("section")
        .prefetch_related("blocks")
        .order_by("order", "id")
    )
    target_count = len(spans)
    current_count = len(cells)

    if current_count == target_count and tuple(cell.span for cell in cells) == tuple(spans):
        if container.layout_key != layout_key:
            container.layout_key = layout_key
            container.save(update_fields=["layout_key", "updated_at"])
        return container

    if target_count < current_count:
        trailing = cells[target_count:]
        # Phase 2B: a Cell holding one or more Blocks through the new
        # multi-block FK is exactly as "not empty" as one holding a legacy
        # single Section — the merge-on-shrink behaviour the owner's V3
        # prototype implements (moving surviving content into the last Cell
        # instead of refusing the resize) is deliberately NOT implemented
        # here (see the Phase 2B report's audit of this function): doing so
        # safely needs its own dedicated design/tests and is left for
        # Phase 2C. Extending this existing guard to also see new-FK Blocks
        # is the minimum required now — it keeps the "never silently delete
        # content" invariant true for multi-block Cells too, by continuing
        # to refuse the shrink rather than silently making Blocks invisible.
        if any(cell.section_id or list(cell.blocks.all()) for cell in trailing):
            raise ContainerLayoutError(
                "خانه‌های اضافی هنوز محتوا دارند. محتوای مخفی هم محتوا محسوب می‌شود؛ "
                "ابتدا آن را حذف یا جابه‌جا کنید، سپس تعداد ستون‌ها را کم کنید"
            )
        StorefrontCell.objects.filter(pk__in=[cell.pk for cell in trailing]).delete()
        cells = cells[:target_count]
    elif target_count > current_count:
        new_cells = [
            StorefrontCell(container=container, order=index, span=spans[index])
            for index in range(current_count, target_count)
        ]
        StorefrontCell.objects.bulk_create(new_cells)
        cells = list(container.cells.select_related("section").order_by("order", "id"))

    for index, (cell, span) in enumerate(zip(cells, spans)):
        cell.order = index
        cell.span = span
    StorefrontCell.objects.bulk_update(cells, ["order", "span"])

    container.layout_key = layout_key
    container.save(update_fields=["layout_key", "updated_at"])
    validate_container(container, list(container.cells.select_related("section").order_by("order", "id")))
    return container

