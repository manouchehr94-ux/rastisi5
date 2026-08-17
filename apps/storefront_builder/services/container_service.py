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
    if total != GRID_UNITS:
        raise ContainerLayoutError(
            f"مجموع عرض خانه‌های چیدمان باید دقیقاً {GRID_UNITS} باشد — مقدار فعلی: {total}"
        )


def validate_page_containers(page) -> None:
    placed_sections = set()
    container_orders = set()
    for container in page.containers.order_by("order", "id").prefetch_related("cells__section"):
        if container.order in container_orders:
            raise ContainerLayoutError("ترتیب Containerهای صفحه تکراری است")
        container_orders.add(container.order)
        cells = list(container.cells.all().order_by("order", "id"))
        validate_container(container, cells)
        for cell in cells:
            if cell.section_id:
                if cell.section_id in placed_sections:
                    raise ContainerLayoutError("یک بخش نمی‌تواند هم‌زمان در دو خانه باشد")
                placed_sections.add(cell.section_id)


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
    return cell


@transaction.atomic
def clone_page_containers(source_page, target_page, target_sections_by_stable_id: dict) -> None:
    """Clone layout placement while preserving logical Container/Cell IDs."""
    target_page.containers.all().delete()
    source_containers = list(
        source_page.containers.prefetch_related("cells__section").order_by("order", "id")
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
        for source_cell in source_container.cells.all().order_by("order", "id"):
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
        if any(cell.section_id for cell in trailing):
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

