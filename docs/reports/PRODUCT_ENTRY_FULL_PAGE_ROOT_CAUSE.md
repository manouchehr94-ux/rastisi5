# Product Entry — Full-Page Architecture: Root-Cause Audit

Baseline: `main` @ `d830f5f` ("product-entry: final verified fixes"), tag `baseline-2026-08-05`.

## 1. Why Create/Edit are modal-only

`apps/dashboard/urls.py` already had semantic-looking routes (`products/add/`,
`products/<pk>/edit/`), but every trigger into them was `hx-get` targeting
`#admin-modal-content` with `@click="modalOpen = true"`:

- `templates/dashboard/products.html` — "➕ افزودن کالای جدید"
- `templates/dashboard/partials/products_table_inner.html` — "✏️" edit button
- `templates/dashboard/product_variants.html` — "✏️ ویرایش کالا" / "تبدیل به کالای دارای تنوع"

The view itself, `product_form()`, never branched on `HX-Request` — it always
rendered the bare fragment `dashboard/partials/product_form.html` (no
`<html>`/sidebar/topbar). A direct browser navigation to
`/admin-portal/products/add/` therefore rendered an unstyled fragment with no
admin chrome — there was no dedicated full-page template at all. This is the
literal cause of problems #1–#3 and #8: the feature was never built as pages,
only as an htmx-swapped fragment for a generic modal container that every
other admin entity (attribute quick-add, category quick-add, product image
manager) also shares.

## 2. Why the variant editor was blocked

`ProductForm` is a plain `forms.Form` (not a `ModelForm`) and requires
`name`, `sku`, `category`, `price` on every submission — including the very
first "keep_open" auto-save. `product_options_body.html` (the real
attribute/variant editor, already a mature, fully server-backed feature) is a
partial that operates against a `Product.pk` — it needs a persisted row to
attach `ProductOption`/`ProductOptionValue`/`ProductVariant` rows to.

Before this fix, `product_form.html`'s price tab only included
`product_options_body.html` when:

```django
{% if product and product.product_type == "variable" %}
```

For a brand-new product, `product` is `None` until the first successful save,
so this branch never rendered. Instead it showed the "ابتدا اطلاعاتِ پایه را
تکمیل کنید" message and relied on a hidden `keep_open` submit button
(`maybeAutoContinueToVariants()` in Alpine) that silently POSTed the *entire*
form the instant `name` + `sku` + `category` were all filled — a genuine
"save behind the merchant's back" hack, and one that:

- never fired at all if the merchant went to the Price tab *first* (matching
  the exact scenario required by task §7 — attributes/variants before Basic
  Info/Category are ever touched);
- required a real, validated Product row to exist before any attribute could
  be created, contradicting "the merchant must not see a separate save-draft-
  first workflow".

This is the literal cause of problems #4–#6.

## 3. Why Edit could (in principle) still fail to show variants immediately

For an *existing* saved product, `product` is never `None`, so the
`{% if product and product.product_type == "variable" %}` gate normally
passed and variants rendered on GET without any extra save. The task's
concern (#7) was more about the *unified* code path than a distinct Edit bug:
once Create and Edit shared one drafting model, both needed to render
`product_options_body.html` unconditionally (not gated on `product_type`),
because the merchant can now flip Simple → Variable *before* the underlying
`product_type` column is updated. That gate has been removed for both Create
and Edit — the panel always renders (client-side `x-show` handles
visibility), for any `product` at all, regardless of category or `product_type`.

## 4. Which conditions were wrong (exact code, before this branch)

| Symptom | File | Condition |
|---|---|---|
| Modal-only Create | `products.html` | `hx-get` + `@click="modalOpen = true"` on the "افزودن کالا" button |
| Modal-only Edit | `products_table_inner.html`, `product_variants.html` | same pattern on "✏️"/"تبدیل به کالای دارای تنوع" |
| Variant tab blocked | `product_form.html` | `{% if product and product.product_type == "variable" %} ... {% else %} <blocking message + hidden keep_open button> {% endif %}` |
| Options context never built for a fresh product | `views.py::_product_form_extra_context` | `if product is not None and product.product_type == Product.ProductType.VARIABLE:` |
| Media required a saved product | `product_form.html` (media tab) | `{% if product %} <real upload UI> {% else %} <browser-only FileReader staging> {% endif %}` |

## 5. Which existing services were reused (no parallel domain built)

Everything attribute/variant/media/SEO-related already existed and is fully
reused, unchanged in logic:

- `product_options_body.html` + its endpoints (`product-option-add`,
  `product-variants-generate`, `product-variant-*`, library attributes,
  category-recommended options) — the real, mature variant engine.
- `product_image_upload` / `product_video_add` and their partials — the real,
  persisted media pipeline (the browser-only staged-file UI is now dead code,
  removed).
- `_product_options_context`, `_product_attribute_field_context`,
  `orphaned_product_attribute_values`, `resolve_category_schema`,
  `validate_product_for_publish` — untouched aside from one defensive fix
  (below).
- `ProductForm` / `_save_product` — untouched validation contract; the
  legacy one-shot `pk=None` POST path (used by ~40 existing tests that create
  a product with a single full-payload POST) is still fully supported,
  byte-for-byte, for backward compatibility.

No new "draft Product" model, no parallel table, no shadow domain — the
existing `Product` row itself becomes the draft, gated by one new boolean.

## 6. Chosen draft architecture

`Product` gains two fields (migration `0033_product_draft_placeholder`):

- `is_draft_placeholder` (bool, default `False`, indexed) — "this row is an
  unfinished creation attempt", **independent of** `status`
  (draft/active/inactive, which is the merchant's own publish-state choice).
  A draft always starts with the model defaults (`status=ACTIVE`,
  `product_type=SIMPLE`, `stock=0`, `unit=PIECE`, …) so the form's visible
  defaults for a brand-new product are unchanged from before.
- `draft_created_by` (nullable FK to the user, `SET_NULL`) — informational
  audit trail only; **not** the access-control boundary (see §7).
- `category` relaxed to `null=True, blank=True` — the only schema relaxation
  needed. A draft is created with `category=None`; `ProductForm.category`
  remains a *required* form field, so finalizing (the only path that can
  flip `is_draft_placeholder` back to `False`) still enforces "must pick a
  real category" exactly as before.

`GET /admin-portal/products/new/` (`product_create_entry`) calls
`get_or_create_product_draft(store, user)`
(`apps/catalog/services/product_draft_service.py`):

1. If the Store already has an `is_draft_placeholder=True` row, resume it
   (redirect to its edit URL) — this is what makes the flow refresh-safe and
   resumable, and it is *why* no separate "save draft first" step exists.
2. Otherwise run the exact same `enforce_can_create_product(store)` gate the
   old code ran inline in `_save_product` for `product is None`, then create
   a new row: `Product.objects.create(store=store, vendor=default_vendor(store), category=None, price=Decimal("0"), is_draft_placeholder=True, draft_created_by=user)`.
3. Redirect (302) to `dashboard:product-edit` for that pk.

`product_form()` (shared by real Edit and draft-resume) is unchanged in
shape: it renders the same full page whether `product` is a real saved
product or a draft. The price tab always includes
`product_options_body.html` once `product` exists at all (see §2/§4) — since
a draft always exists from the very first GET, attributes/variants/media can
be added immediately, in any order, before Basic Info or Category are ever
touched.

Finalizing: the very first *validated* save (through the untouched
`ProductForm`/`_save_product` contract — name + sku + category + price all
required) sets `is_draft_placeholder = False` unconditionally. From that
point the row is a completely ordinary `Product`.

One more gap surfaced by making the variant editor always-present: `product.product_type`
itself previously only ever changed as part of a full `ProductForm` submission
(`set_product_type()`, called from `product_form`'s POST handler). Since the
"کالای دارای تنوع" segment toggle is now available from the very first page
load — before the merchant has ever submitted the main form — clicking it only
changed client-side Alpine state; the underlying row stayed `product_type=simple`
in the database, and `generate_variants()` (which requires
`product_type=VARIABLE`) would reject the exact §7 scenario. Fixed with one
small, focused addition: `POST /admin-portal/products/<pk>/type/`
(`product_set_type`), an htmx call wired to the segment buttons that persists
the type change immediately via the existing, unchanged `set_product_type()`
service function (including its existing safety rule — variable→simple is
blocked while variants exist). This is the same "small AJAX endpoint next to
the existing options partial" pattern already used for every other
attribute/variant operation — not a new mechanism.

### Draft visibility exclusion

`is_draft_placeholder=True` rows are excluded from every place merchants or
the storefront ever see a product count/listing, since `status` alone no
longer implies "real, finished product":

- `apps.dashboard.services.catalog_admin_service.filtered_products` (the
  product list table)
- `apps.dashboard.views._product_list_context` stats row
- `apps.dashboard.services.dashboard_service` (dashboard KPI cards, low-stock
  widget, nav product count)
- `apps.dashboard.services.checklist_service` (onboarding checklist)
- `apps.dashboard.context_processors` (sidebar nav badge)
- `apps.subscriptions.services.usage_service._count_products` (plan/usage
  limit — so an abandoned draft never eats into the merchant's product quota)
- `apps.catalog.services.product_publish_service.storefront_visible_products`
  (defense in depth: a draft's `status` defaults to `ACTIVE`, so this filter
  is the one that actually keeps a draft out of the storefront if it's ever
  reached with that status)

## 7. Draft ownership, tenant isolation, cleanup

- **Store ownership / tenant isolation**: identical mechanism to every other
  Product operation in this codebase — `get_object_or_404(Product, pk=pk,
  store=store)`, where `store` comes from `_resolve_dashboard_store(request)`
  (host + membership resolved, fail-closed). A guessed pk belonging to
  another Store 404s exactly like it would for any other product. No new
  access-control primitive was introduced.
- **Creator/session ownership**: `draft_created_by` is informational only.
  Resumption is scoped by *Store*, not by the individual staff user, matching
  the task's explicitly offered design ("one resumable recent Product draft
  per merchant/**store** creation flow"). This also sidesteps a real
  constraint: `(store, sku)` and `(store, slug)` are unique, and a draft is
  created with both blank — a second concurrent "new" attempt in the same
  Store necessarily resumes the first draft rather than colliding on the
  unique constraint.
- **No guessed-ID access**: pk-based, store-scoped, same as the rest of the
  app (this codebase does not use UUIDs for Product anywhere; introducing one
  only for drafts would be an inconsistent, unrequested parallel scheme).
- **Explicit Cancel**: `POST /admin-portal/products/<pk>/discard-draft/`
  (`product_discard_draft`), only reachable for
  `is_draft_placeholder=True` rows owned by the resolved Store, requires a
  client-side `confirm()` before submitting. Deletes the row and its
  `ProductImage` files (`_delete_product_and_files` explicitly calls
  `.image.delete(save=False)`/`.thumbnail.delete(save=False)` before
  `product.delete()`, mirroring the existing `delete_product_image` pattern —
  Django never deletes files on row delete by itself).
- **Abandoned-draft cleanup**: `cleanup_stale_product_drafts(older_than_hours=48)`
  in `product_draft_service.py`, wired to the new management command
  `python manage.py cleanup_stale_product_drafts [--older-than-hours N]`.
  Filters on `updated_at` (not `created_at`), so any GET on the draft's edit
  page (`touch_product_draft`, called on every successful GET while
  `is_draft_placeholder=True`) resets the timer — an actively-worked draft is
  never at risk. Idempotent: re-running finds nothing once already cleaned;
  safe to run on a schedule (cron/Celery beat), same pattern as the existing
  `expire_inventory_reservations` command.

## 8. Migration implications

Single migration, purely additive/relaxing:

- `AddField(is_draft_placeholder, default=False)` — safe on existing rows,
  no data migration needed (all existing products get `False`, i.e.
  unaffected).
- `AddField(draft_created_by, null=True)` — safe.
- `AlterField(category, null=True, blank=True)` — relaxes a constraint; does
  not touch existing data (every existing row already has a category).

One defensive follow-on fix was required by this relaxation:
`apps.catalog.services.category_schema_service.resolve_category_schema`
previously assumed `category` was never `None` (true before this change) and
crashed (`AttributeError` in `_ancestor_chain`) the moment a draft with
`category=None` reached it via `orphaned_product_attribute_values`. Fixed at
the single choke point (`resolve_category_schema` now returns `[]` for
`None`) rather than patching each of its four call sites.

`python manage.py makemigrations --check --dry-run` is clean after this
migration (verified).

## 9. Rollback plan

The migration is reversible with Django's standard `migrate catalog
<previous>` as long as no row has been created with `category=None` at the
time of rollback (SQLite/Postgres will refuse to make the column `NOT NULL`
again while such rows exist). In practice: run
`python manage.py cleanup_stale_product_drafts --older-than-hours 0` (or
finalize/discard any remaining drafts) immediately before rolling back, then
`Product.objects.filter(is_draft_placeholder=True).delete()` as a last
resort — drafts are by definition disposable, unfinished creation attempts,
never a real merchant's finished product. No other rollback step is needed:
reverting the view/template/urls changes in this branch simply restores the
old modal flow against the same `Product` table (the two new fields are
additive and inert if the code stops setting them).

## 10. Also fixed while unifying the flow

- `messages.success(...)` calls added to `product_form`'s success path
  collided with a pre-existing local variable named `messages` inside the
  `except ValidationError` handler (`for field, messages in
  exc.message_dict.items()`), which Python treats as shadowing the
  module-level `django.contrib.messages` import for the *entire* function
  body, not just that branch. Renamed the loop variable
  (`field_messages`) — this was a latent landmine that simply had never been
  exercised before, since `product_form` never called `messages.*` on the
  success path in the modal-based version.
