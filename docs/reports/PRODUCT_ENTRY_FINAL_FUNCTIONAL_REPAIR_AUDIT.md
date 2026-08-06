# Product Entry — Final Functional Repair: Root-Cause Audit

Every defect below was reproduced in a real headless-Chromium browser against
the running Django app (network requests, response bodies, and database state
were all inspected directly) before any code was changed, per the task's
"reproduce first" requirement. Each finding lists the exact file/line, the
exact mechanism of failure, and the fix applied.

## 1. Save buttons ("ذخیره کالا" top, "ثبت کالا" bottom, "ذخیره‌ی پیش‌نویس")

**They already share one canonical form, one view, one validation
pipeline** (`<form id="productSaveForm">` → `apps/dashboard/views.py:product_form`).
There is no divergent second implementation to unify. Two real, distinct
defects made all three buttons appear broken:

### 1a. Category "گروهِ اصلی" (main group) select resets on every failed save

- File: `apps/dashboard/views.py`, `product_form()` (fallthrough branch after
  `if form.is_valid():`) and `_product_form_extra_context()`.
- Mechanism: the "زیرگروه" (leaf) `<select name="category">` is a two-step
  cascading picker — the "گروهِ اصلی" `<select>` had **no `name` attribute**,
  so it was never submitted to the server at all. On the very first save
  attempt of a new product (before a leaf category is chosen), the whole
  `ProductForm` fails validation; the re-rendered page then computed
  `category = product.category if product else None` — for a brand-new
  draft this is always `None`, so `selected_category_group_id` (used to
  pre-select "گروهِ اصلی" on reload) was always empty. The merchant had to
  re-pick the main group on every attempt, while the leaf select stayed
  empty — an effective infinite loop where Save never succeeds.
- Fix: gave the group `<select>` a real `name="category_group"`
  (`product_category_select.html`), and made `product_form()` /
  `_product_form_extra_context()` prefer the *submitted* category/group
  (even when invalid) over the product's already-saved one when
  reconstructing the reload context.
- Verified: Playwright — pick group only (no leaf) → Save → group selection
  now survives the reload; only the leaf needs to be picked to finish.

### 1b. "ذخیره‌ی پیش‌نویس" always failed when price was left blank

- File: `apps/dashboard/forms.py`, `ProductForm.price` / `clean_price`.
- Mechanism: `price = forms.CharField(label="قیمت (تومان)")` — no
  `required=False`. Django's own base-field required-check raised "این
  فیلد لازم است" *before* the custom `clean_price()` method (which already
  had draft-aware logic) ever ran. The draft button's own tooltip promises
  "فیلدهای الزامی (نام، کد کالا، دسته‌بندی) هنوز باید پر شده باشند" — price
  is explicitly *not* supposed to be required for a draft, and
  `validate_product_for_publish()` already separately enforces price > 0
  before a product can go Active. This one field's `required=True` broke
  the very use case a draft-save button exists for.
- Fix: `price` field is now `required=False`; `clean_price()` returns `0`
  when blank **and** the submitted `status` is `draft` (mirroring the
  existing `clean_stock` pattern), otherwise still enforces `min_value=1`
  exactly as before.
- Verified: Playwright — fill name/SKU/category, leave price blank, click
  "ذخیره‌ی پیش‌نویس" → product now saves with `status=draft`, `price=0`;
  the same blank price with `status=active` still correctly fails (no
  regression on the publish-time requirement).

No other save-path defect was found: bottom "ثبت کالا" and top "ذخیره کالا"
were re-tested independently after both fixes and persist correctly.

## 2. Variant bulk actions (تنظیم گروهی موجودی / فعال‌سازی / غیرفعال‌سازی)

- File: `apps/dashboard/templates/dashboard/partials/product_options_body.html`
  — `checkedIds()`, `bulkFill()`, `bulkActivate()`, `applyBulkSalesLimit()`.
- Root cause (confirmed via direct instrumentation of the live page):
  `checkedIds()` used `this.$el.querySelectorAll('tbody input[name=delete_variant_ids]:checked, ...')`.
  Alpine's `$el` magic property, **when accessed from inside a method
  invoked via a `@click` directive, is scoped to the element the click
  fired on** (the bulk-action `<button>` itself — a childless leaf node),
  not to the `x-data` root. So every real click on a bulk button searched
  for checkboxes *inside the button*, always found zero, and the function
  returned before ever calling `htmx.ajax()`. This is why **every** bulk
  action silently did nothing in a real browser, while direct
  programmatic invocation (bypassing the click) worked and looked
  "correct" in isolation — the bug only manifests on a genuine click.
- Fix: scoped all three lookups to the stable ancestor id
  `#productOptionsBody` via `document.querySelector(...)` instead of
  `this.$el`, eliminating the per-click rebinding hazard entirely.
- Additionally implemented section 6's explicit requirement: replaced the
  native `window.prompt()` + "you must also click ذخیره‌ی تغییرات
  afterward" two-step flow for bulk stock with a proper small modal
  (`bulkStockOpen`/`applyBulkStock()`, mirroring the already-correct
  `bulkSalesLimitOpen` pattern) that validates and applies immediately via
  a new dedicated endpoint `product-variants-bulk-stock`
  (`product_variants_bulk_stock` view).
- Verified with real checkbox selections + real clicks: bulk activate,
  deactivate, stock, and sales-limit each affect **only** the checked rows
  and persist to the database on the same click, with no separate save
  step. Bulk delete (a plain `hx-post` button, not part of this
  `checkedIds()` mechanism) was already working correctly and is
  unaffected.

## 3. Explicit active/inactive status

The table view already renders explicit Persian text ("فعال"/"غیرفعال")
next to the toggle, not a bare checkbox or lone checkmark; the card view
already renders a read-only text pill. This already satisfies the
requirement — no code change was needed here beyond the bulk-action fix
above (which is what actually let bulk (de)activation reach the database).

## 4. Product image upload — click-to-select

- File: `apps/dashboard/templates/dashboard/partials/product_form.html`,
  the `.dropzone` `<label>`.
- Root cause: `@click.prevent="$refs.editImagesInput.click()"` called
  `preventDefault()` on the label's click event. A `<label>` that visually
  *wraps* its associated `<input type="file">` (as this one does) already
  has a **native browser behavior**: clicking the label forwards the
  activation to the input and opens the file picker, with no JavaScript
  required. Calling `preventDefault()` explicitly suppresses that native
  forwarding — and the manual `$refs.editImagesInput.click()` replacement
  did not reliably reopen the picker (confirmed to fail 3/3 in real
  headless-Chromium; the click event fired, but no file chooser ever
  appeared).
- Fix: removed the redundant/harmful `@click.prevent` handler entirely —
  the label's implicit native association with its nested `<input>` is
  sufficient and is the standard, dependency-free pattern for custom file
  dropzones.
- Verified 3/3 clean runs: click opens the native picker
  (`multiple=True`); a real JPEG upload through it round-trips through the
  existing `product-image-upload` htmx endpoint and appears as the cover
  image with alt/caption fields, exactly as designed. Drag-and-drop
  (`@drop.prevent`) was untouched and continues to work.

## 5. Product video — YouTube / Aparat / Instagram

- **Pre-existing, confirmed bug (not caused by this session): video could
  never be added at all, for *any* provider.** File:
  `apps/dashboard/views.py`, `product_video_add()`. The template posts the
  URL/title fields as `__edit_video_url` / `__edit_video_title`
  (dunder-prefixed specifically to avoid colliding with other Product-form
  fields), but the view read `request.POST.get("url")` /
  `request.POST.get("title")` — keys that never existed in the POST body.
  Every submission therefore received an empty string, which
  `detect_provider_and_id()` always rejects as "این لینک شناخته‌شده
  نیست", regardless of how valid the pasted link actually was. Fixed by
  reading the correct field names (with a defensive fallback to the old
  `url`/`title` names, in case any other caller used them).
- **Second, separate bug, specific to real clicks:** the "افزودنِ ویدیو"
  button had `@click="url = ''; embedUrl = ''"` on the *same* element as
  its `hx-post`. Alpine's `@click` and htmx's own click-triggered request
  both listen on that element's `click` event; the Alpine handler ran
  first and reset the `x-model`-bound `url`, wiping the input's value
  before htmx read it for the request — reproducing exactly the hazard
  already documented (and already correctly worked around) for the
  category quick-add modal elsewhere in this same file. Fixed the same
  way: moved the reset to `hx-on::htmx:before-request`, which fires after
  htmx has already captured the request payload.
- **Instagram support added:** `ProductVideo.Provider.INSTAGRAM` (new
  migration `0034_alter_productvideo_provider_add_instagram.py`, choices
  metadata only, no data migration needed); `detect_provider_and_id()`
  now accepts `instagram.com/(p|reel|tv)/<shortcode>` and rejects bare
  profile/home URLs. Since Instagram does not reliably support anonymous
  iframe embedding without their own JS widget, `embed_url()` returns
  `None` for Instagram and the video list instead renders a safe,
  clearly-labelled link card that opens the original public post/Reel in
  a new tab (`instagram_permalink` property) — matching the task's own
  explicit instruction not to claim embed support the platform doesn't
  reliably provide.
- Verified end-to-end: one YouTube URL, one Aparat URL, and one Instagram
  Reel URL were all added in the same session and persisted correctly
  (confirmed via direct DB read); an unrecognized URL (`example.com/...`)
  is correctly rejected with the button staying disabled and an inline
  Persian error shown.

## 6. Rich-text description editor

**It was never removed — it silently failed to mount.** File:
`apps/dashboard/templates/dashboard/base_admin.html`. CKEditor 5 (Classic
Build, GPL, Persian toolbar: headings, bold/italic, lists, link, table,
image, media embed, undo/redo) and its Persian translation file were
already vendored and already wired up (`richTextEditor()` /
`x-data="richTextEditor()" x-init="mount()"` on the description field).
The four `<script defer>` tags execute in **document order**:
`htmx.min.js`, `alpine.min.js`, `ckeditor.js`, `translations-fa.js`.
Because Alpine ran *before* `ckeditor.js` finished executing,
`x-init="mount()"` always ran while `window.ClassicEditor` was still
`undefined` — and `mount()` deliberately no-ops silently
(`if (typeof ClassicEditor === "undefined") return;`) rather than
throwing, so nothing ever appeared in the console to explain why the
field stayed a plain `<textarea>`.

Fix: reordered the script tags so both CKEditor scripts load and execute
**before** `alpine.min.js`. Server-side sanitization
(`sanitize_product_description` in `apps/catalog/services/html_sanitizer.py`,
already called from `ProductForm.clean_description`) was untouched — it
was already correct and simply unreachable because the editor never
mounted.

Verified: the full CKEditor toolbar now renders in the "توضیحات کالا"
field; typed **bold** text was saved and, after reopening the product,
round-tripped back into the editor exactly as `<p><strong>...</strong></p>`.

## Files changed

- `apps/dashboard/views.py` — category-group preservation on invalid POST;
  new `product_variants_bulk_stock` view; fixed `product_video_add` field
  names.
- `apps/dashboard/forms.py` — `ProductForm.price` optional for drafts.
- `apps/dashboard/urls.py` — new `product-variants-bulk-stock` route.
- `apps/dashboard/templates/dashboard/partials/product_category_select.html`
  — named the main-group select.
- `apps/dashboard/templates/dashboard/partials/product_options_body.html`
  — `$el` → `#productOptionsBody`-scoped lookups; new bulk-stock modal.
- `apps/dashboard/templates/dashboard/partials/product_form.html` — image
  dropzone native-label fix; video form Instagram support + before-request
  timing fix.
- `apps/dashboard/templates/dashboard/partials/product_videos_list.html` —
  safe Instagram link-preview card.
- `apps/dashboard/templates/dashboard/base_admin.html` — CKEditor script
  order.
- `apps/catalog/models.py` — `ProductVideo.Provider.INSTAGRAM`,
  `instagram_permalink` property.
- `apps/catalog/services/product_video_service.py` — Instagram detection
  and safe (non-iframe) handling.
- `apps/catalog/migrations/0034_alter_productvideo_provider_add_instagram.py`
  — new choice value only, no schema change.

## Explicitly out of scope / unchanged

- Product Entry draft lifecycle, five-tab layout, category quick-add,
  brand quick-add, simplified attribute cards, add-value request scoping
  (fixed in the prior session), Cartesian variant generation, table/card
  views, mobile responsiveness, SEO/publication fields — all untouched.
- No redesign of any page. No new Product form. No change to the variant
  engine or its models beyond the additive, non-destructive
  `ProductVideo.Provider` choice.
