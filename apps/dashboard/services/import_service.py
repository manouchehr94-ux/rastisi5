"""موتورِ واردات CSV (Import) — کالا/تنوع/موجودی — checkpoint 4B.

نگاه کنید به ADR-55 (چرخه‌ی عمرِ Job)، ADR-56 (اتمیکیِ دسته‌ای)، ADR-57
(تشخیصِ هویتِ پایدار)، ADR-58 (یکپارچگیِ سرویسِ کالا)، ADR-59 (تنوع و
موتورِ تنوع)، ADR-60 (موجودی و ایمنیِ رزرو)، ADR-61 (idempotency) در
``SAAS_DOMAIN_DECISIONS.md``.

**قاعده‌ی طلایی**: پیش‌نمایش (dry-run) و اجرا از دقیقاً همان مسیرِ
اعتبارسنجی عبور می‌کنند — ``_validate_product_row``/``_validate_variant_row``/
``_validate_inventory_row`` هیچ‌گاه دو نسخه ندارند؛ فقط پارامترِ
``dry_run`` تعیین می‌کند که آیا در انتها چیزی در دیتابیس نوشته شود یا نه."""

from dataclasses import dataclass, field as dataclass_field

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product
from apps.catalog.services.inventory_service import adjust_stock_manually
from apps.core.models import ImportJob, ImportRowResult
from apps.core.services.audit_service import record_audit_event
from apps.core.services.csv_utils import (
    normalize_import_text,
    parse_import_bool,
    parse_import_decimal,
    parse_import_int,
    read_csv_rows_bounded,
    validate_csv_upload,
)
from apps.dashboard.services.catalog_admin_service import default_vendor, generate_unique_slug
from apps.orders.models import TaxClass

DEFAULT_BATCH_SIZE = 100

PRODUCT_STATUS_VALUES = {choice for choice, _ in Product.Status.choices}


class ImportServiceError(Exception):
    """خطای سطحِ Job (نه ردیف) — مثلاً حالتِ اجرا یا نوعِ واردات نامعتبر است."""


@dataclass
class RowOutcome:
    row_number: int
    source_identifier: str
    status: str  # valid / invalid / created / updated / skipped / failed
    errors: list = dataclass_field(default_factory=list)
    warnings: list = dataclass_field(default_factory=list)
    target_object_type: str = ""
    target_object_id: int | None = None
    normalized_data_summary: dict = dataclass_field(default_factory=dict)


# ================================================================== کالا (Product)

def _product_lookup_cache(store, rows: list[dict]) -> dict:
    """پیش‌واکشیِ یک‌جای مرجع‌هایِ Store-scoped — به‌جایِ یک کوئری به‌ازایِ
    هر سلولِ CSV (checkpoint 4B §26). فقط شناسه‌هایی که واقعاً در فایل
    ارجاع شده‌اند واکشی می‌شوند، نه کلِ کاتالوگ."""
    product_ids = set()
    skus = set()
    for row in rows:
        raw_id = normalize_import_text(row.get("product_id"))
        if raw_id.isdigit():
            product_ids.add(int(raw_id))
        sku = normalize_import_text(row.get("sku"))
        if sku:
            skus.add(sku)

    products_by_id = {
        p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids).select_related("brand", "category", "tax_class")
    }
    products_by_sku = {
        p.sku: p for p in Product.objects.filter(store=store, sku__in=skus).select_related("brand", "category", "tax_class")
    }
    foreign_product_ids = set(
        Product.objects.filter(pk__in=product_ids).exclude(store=store).values_list("pk", flat=True)
    )
    return {
        "products_by_id": products_by_id,
        "products_by_sku": products_by_sku,
        "foreign_product_ids": foreign_product_ids,
        "brands_by_slug": {b.slug: b for b in Brand.objects.filter(store=store)},
        "categories_by_slug": {c.slug: c for c in Category.objects.filter(store=store, parent__isnull=False)},
        "tax_classes_by_code": {t.code: t for t in TaxClass.objects.filter(store=store)},
        "default_vendor": default_vendor(store),
    }


def _resolve_product_identity(store, row: dict, *, cache: dict):
    """اولویتِ هویتِ پایدار (checkpoint 4B §7): شناسه‌ی Store-scoped >
    SKUِ Store-scoped > بدونِ تطبیق. یک شناسه‌ی متعلق به Store دیگر همیشه
    خطا است — هرگز بی‌صدا به SKU سقوط نمی‌کند."""
    raw_id = normalize_import_text(row.get("product_id"))
    if raw_id:
        if not raw_id.isdigit():
            return None, f"«product_id» نامعتبر است: {raw_id}"
        product_id = int(raw_id)
        if product_id in cache["foreign_product_ids"]:
            return None, "این شناسه‌ی کالا متعلق به فروشگاه دیگری است."
        product = cache["products_by_id"].get(product_id)
        if product is None:
            return None, f"کالایی با شناسه‌ی «{product_id}» در این فروشگاه یافت نشد."
        return product, None

    sku = normalize_import_text(row.get("sku"))
    if sku:
        return cache["products_by_sku"].get(sku), None

    return None, None


def _validate_product_row(row_number: int, row: dict, *, store, mode: str, cache: dict) -> tuple[RowOutcome, dict | None, "Product | None"]:
    """اعتبارسنجیِ یک ردیفِ واردات کالا — چه در پیش‌نمایش چه در اجرا صدا
    زده می‌شود. خروجی: (نتیجه، دیکشنریِ فیلدهایِ نرمال‌شده یا None اگر
    نامعتبر، Productِ هدف یا None اگر ایجادِ تازه لازم است)."""
    errors, warnings = [], []
    sku = normalize_import_text(row.get("sku"))
    source_identifier = normalize_import_text(row.get("product_id")) or sku or f"row-{row_number}"

    existing_product, identity_error = _resolve_product_identity(store, row, cache=cache)
    if identity_error:
        errors.append(identity_error)

    is_update = existing_product is not None
    if mode == ImportJob.Mode.CREATE_ONLY and is_update:
        errors.append("این ردیف با کالایِ موجود مطابقت دارد؛ حالتِ «فقط ایجاد» آن را رد می‌کند.")
    if mode == ImportJob.Mode.UPDATE_ONLY and not is_update and not identity_error:
        errors.append("این ردیف با هیچ کالایِ موجودی مطابقت ندارد؛ حالتِ «فقط به‌روزرسانی» آن را رد می‌کند.")

    name = normalize_import_text(row.get("name"))
    if not name and not is_update:
        errors.append("«name» برایِ ایجادِ کالایِ تازه الزامی است.")
    elif not name and is_update:
        name = existing_product.name

    if sku and not is_update:
        # SKU باید در همین Store یکتا باشد؛ برخوردِ آن با کالایِ دیگر (نه
        # همان کالایِ در حالِ به‌روزرسانی) خطاست.
        clashing = cache["products_by_sku"].get(sku)
        if clashing is not None and (existing_product is None or clashing.pk != existing_product.pk):
            errors.append(f"SKUِ «{sku}» قبلاً به کالایِ دیگری اختصاص دارد.")

    status = normalize_import_text(row.get("status")) or (existing_product.status if is_update else Product.Status.ACTIVE)
    if status not in PRODUCT_STATUS_VALUES:
        errors.append(f"وضعیتِ «{status}» نامعتبر است.")

    price = None
    try:
        price = parse_import_decimal(row.get("price"), field_name="قیمت")
    except ValueError as exc:
        errors.append(str(exc))
    if price is None and not is_update:
        errors.append("«price» برایِ ایجادِ کالایِ تازه الزامی است.")
    elif price is not None and price < 0:
        errors.append("قیمت نمی‌تواند منفی باشد.")

    stock = None
    try:
        stock = parse_import_int(row.get("stock"), field_name="موجودی")
    except ValueError as exc:
        errors.append(str(exc))
    if stock is not None and stock < 0:
        errors.append("موجودی نمی‌تواند منفی باشد.")

    weight_grams = None
    try:
        weight_grams = parse_import_int(row.get("weight_grams"), field_name="وزن")
    except ValueError as exc:
        errors.append(str(exc))

    requires_shipping = True
    try:
        requires_shipping = parse_import_bool(
            row.get("requires_shipping"),
            default=existing_product.requires_shipping if is_update else True,
        )
    except ValueError as exc:
        errors.append(str(exc))

    brand = None
    brand_code = normalize_import_text(row.get("brand_code"))
    if brand_code:
        brand = cache["brands_by_slug"].get(brand_code)
        if brand is None:
            errors.append(f"برندِ «{brand_code}» در این فروشگاه یافت نشد.")

    category = None
    category_code = normalize_import_text(row.get("category_code"))
    if category_code:
        category = cache["categories_by_slug"].get(category_code)
        if category is None:
            errors.append(f"دسته‌بندیِ «{category_code}» در این فروشگاه یافت نشد (یا زیردسته نیست).")
    elif not is_update:
        errors.append("«category_code» برایِ ایجادِ کالایِ تازه الزامی است.")

    tax_class = None
    tax_class_code = normalize_import_text(row.get("tax_class_code"))
    tax_class_cleared = False
    if tax_class_code:
        tax_class = cache["tax_classes_by_code"].get(tax_class_code)
        if tax_class is None:
            errors.append(f"دسته‌ی مالیاتیِ «{tax_class_code}» در این فروشگاه یافت نشد.")
        elif not tax_class.is_active:
            warnings.append(f"دسته‌ی مالیاتیِ «{tax_class_code}» غیرفعال است.")
    elif "tax_class_code" in row and is_update:
        tax_class_cleared = True  # explicit empty column value on update → clear override

    vendor = cache["default_vendor"]
    if not is_update and vendor is None:
        errors.append("این فروشگاه هنوز هیچ فروشنده‌ای ندارد؛ کالای تازه قابل‌ایجاد نیست.")

    if errors:
        outcome = RowOutcome(
            row_number=row_number, source_identifier=source_identifier, status=ImportRowResult.RowStatus.INVALID,
            errors=errors, warnings=warnings,
        )
        return outcome, None, existing_product

    normalized = {
        "name": name, "sku": sku, "slug": normalize_import_text(row.get("slug")),
        "barcode": normalize_import_text(row.get("barcode")),
        "status": status, "price": price, "stock": stock, "weight_grams": weight_grams,
        "requires_shipping": requires_shipping,
        "brand": brand, "category": category, "tax_class": tax_class, "tax_class_cleared": tax_class_cleared,
        "seo_title": normalize_import_text(row.get("seo_title")),
        "seo_description": normalize_import_text(row.get("seo_description")),
    }
    outcome = RowOutcome(
        row_number=row_number, source_identifier=source_identifier, status=ImportRowResult.RowStatus.VALID,
        warnings=warnings,
    )
    return outcome, normalized, existing_product


def _apply_product_row(*, store, normalized: dict, existing_product, vendor, actor) -> tuple[Product, bool]:
    """اعمالِ واقعیِ یک ردیفِ معتبر — فقط از مسیرِ سرویس/مدل (``full_clean``،
    ``generate_unique_slug``، ``adjust_stock_manually``) — هرگز موجودی را
    مستقیم نمی‌نویسد (checkpoint 4B §8/§10). ``vendor`` فقط برایِ ایجادِ
    کالایِ تازه لازم است (Store-scoped، از ``default_vendor`` در کش)."""
    is_create = existing_product is None
    product = existing_product or Product(store=store, vendor=vendor, category=normalized["category"])

    if not is_create and normalized["category"] is not None:
        product.category = normalized["category"]

    product.name = normalized["name"]
    if normalized["sku"]:
        product.sku = normalized["sku"]
    elif is_create:
        product.sku = ""
    product.slug = normalized["slug"] or generate_unique_slug(Product, normalized["name"], store=store, instance=product)
    if normalized["barcode"]:
        product.barcode = normalized["barcode"]
    product.status = normalized["status"]
    if normalized["weight_grams"] is not None:
        product.weight_grams = normalized["weight_grams"]
    product.requires_shipping = normalized["requires_shipping"]
    if normalized["brand"] is not None:
        product.brand = normalized["brand"]
    if normalized["tax_class"] is not None:
        product.tax_class = normalized["tax_class"]
    elif normalized["tax_class_cleared"]:
        product.tax_class = None
    if normalized["price"] is not None:
        product.price = normalized["price"]
    if normalized["seo_title"]:
        product.seo_title = normalized["seo_title"]
    if normalized["seo_description"]:
        product.seo_description = normalized["seo_description"]

    product.full_clean(exclude=["stock"])
    product.save()

    if normalized["stock"] is not None:
        adjust_stock_manually(store=store, product=product, new_stock=normalized["stock"], actor=actor, note="Import")

    return product, is_create


# ================================================================== موتورِ اجرایِ عمومی

def _chunked(sequence: list, size: int):
    for start in range(0, len(sequence), size):
        yield sequence[start:start + size]


@transaction.atomic
def _execute_product_batch(store, batch, *, mode, cache, actor, dry_run: bool) -> list[RowOutcome]:
    from django.core.exceptions import ValidationError

    outcomes = []
    for row_number, row in batch:
        outcome, normalized, existing_product = _validate_product_row(row_number, row, store=store, mode=mode, cache=cache)
        if normalized is None:
            outcomes.append(outcome)
            continue
        if dry_run:
            outcomes.append(outcome)
            continue
        try:
            product, is_create = _apply_product_row(
                store=store, normalized=normalized, existing_product=existing_product,
                vendor=cache["default_vendor"], actor=actor,
            )
            outcome.status = ImportRowResult.RowStatus.CREATED if is_create else ImportRowResult.RowStatus.UPDATED
            outcome.target_object_type = "Product"
            outcome.target_object_id = product.pk
            # کش را برایِ ردیف‌هایِ بعدیِ همین اجرا هم‌راستا نگه می‌دارد (مثلاً
            # دو ردیف که یکی کالا می‌سازد و دیگری با SKUِ همان کالا آن را
            # به‌روزرسانی می‌کند).
            cache["products_by_sku"][product.sku] = product
            cache["products_by_id"][product.pk] = product
        except ValidationError as exc:
            outcome.status = ImportRowResult.RowStatus.FAILED
            messages = sum(exc.message_dict.values(), []) if hasattr(exc, "message_dict") else exc.messages
            outcome.errors.extend(messages)
        except Exception as exc:  # noqa: BLE001 — یک ردیفِ ناموفق نباید کل Job را متوقف کند
            outcome.status = ImportRowResult.RowStatus.FAILED
            outcome.errors.append(str(exc))
        outcomes.append(outcome)
    return outcomes


_BATCH_EXECUTORS = {
    ImportJob.ImportType.PRODUCTS: (_product_lookup_cache, _execute_product_batch),
}


def run_import(job: ImportJob, rows: list[dict], *, actor, batch_size: int = DEFAULT_BATCH_SIZE) -> ImportJob:
    """موتورِ عمومیِ پیش‌نمایش/اجرا — برایِ هر سه نوعِ واردات یکسان است
    (checkpoint 4B §16). ``job.dry_run`` تعیین می‌کند پیش‌نمایش است یا اجرا؛
    ``job.status`` بر همان اساس تنظیم می‌شود. هر batch در تراکنشِ اتمیکِ
    خودش اجرا می‌شود — شکستِ یک batch سایرِ batchهایِ موفق را برنمی‌گرداند
    (ADR-56)."""
    if job.import_type not in _BATCH_EXECUTORS:
        raise ImportServiceError(f"نوعِ واردات «{job.import_type}» پشتیبانی نمی‌شود.")
    build_cache, execute_batch = _BATCH_EXECUTORS[job.import_type]

    job.status = ImportJob.Status.VALIDATING if job.dry_run else ImportJob.Status.PROCESSING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    cache = build_cache(job.store, rows)
    numbered_rows = list(enumerate(rows, start=1))

    all_outcomes: list[RowOutcome] = []
    for batch in _chunked(numbered_rows, batch_size):
        all_outcomes.extend(
            execute_batch(job.store, batch, mode=job.mode, cache=cache, actor=actor, dry_run=job.dry_run)
        )

    ImportRowResult.objects.filter(import_job=job).delete()
    ImportRowResult.objects.bulk_create([
        ImportRowResult(
            import_job=job, row_number=o.row_number, source_identifier=o.source_identifier[:120],
            status=o.status, errors=o.errors, warnings=o.warnings,
            target_object_type=o.target_object_type, target_object_id=o.target_object_id,
            normalized_data_summary=o.normalized_data_summary,
        )
        for o in all_outcomes
    ])

    counts = {status: 0 for status in (
        ImportRowResult.RowStatus.VALID, ImportRowResult.RowStatus.INVALID,
        ImportRowResult.RowStatus.CREATED, ImportRowResult.RowStatus.UPDATED,
        ImportRowResult.RowStatus.SKIPPED, ImportRowResult.RowStatus.FAILED,
    )}
    for o in all_outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1

    job.total_rows = len(all_outcomes)
    job.valid_rows = counts[ImportRowResult.RowStatus.VALID]
    job.invalid_rows = counts[ImportRowResult.RowStatus.INVALID]
    job.created_rows = counts[ImportRowResult.RowStatus.CREATED]
    job.updated_rows = counts[ImportRowResult.RowStatus.UPDATED]
    job.skipped_rows = counts[ImportRowResult.RowStatus.SKIPPED]
    job.failed_rows = counts[ImportRowResult.RowStatus.FAILED]
    job.completed_at = timezone.now()

    if job.dry_run:
        job.status = ImportJob.Status.PREVIEW_READY
    elif job.total_rows == 0:
        job.status = ImportJob.Status.FAILED
        job.error_summary = "فایل هیچ ردیفی نداشت."
    elif job.failed_rows == 0 and job.invalid_rows == 0:
        job.status = ImportJob.Status.COMPLETED
    elif job.created_rows == 0 and job.updated_rows == 0:
        job.status = ImportJob.Status.FAILED
        job.error_summary = f"{job.invalid_rows} ردیفِ نامعتبر، {job.failed_rows} ردیفِ ناموفق."
    else:
        job.status = ImportJob.Status.COMPLETED_WITH_ERRORS
        job.error_summary = f"{job.invalid_rows} ردیفِ نامعتبر، {job.failed_rows} ردیفِ ناموفق."

    job.save(update_fields=[
        "total_rows", "valid_rows", "invalid_rows", "created_rows", "updated_rows",
        "skipped_rows", "failed_rows", "completed_at", "status", "error_summary",
    ])

    action_code = "import.preview_completed" if job.dry_run else "import.execution_completed"
    record_audit_event(
        store=job.store, actor=actor, action_code=action_code,
        object_type="ImportJob", object_id=str(job.pk),
        object_label=f"{job.get_import_type_display()} — {job.total_rows} ردیف",
        after={
            "total_rows": job.total_rows, "valid_rows": job.valid_rows, "invalid_rows": job.invalid_rows,
            "created_rows": job.created_rows, "updated_rows": job.updated_rows,
            "skipped_rows": job.skipped_rows, "failed_rows": job.failed_rows, "status": job.status,
        },
    )
    return job


# ================================================================== چرخه‌ی عمرِ Job (آپلود/پیش‌نمایش/اجرا)

def create_import_job(store, *, import_type: str, uploaded_file, mode: str, requested_by, idempotency_key: str = "") -> ImportJob:
    """یک ``ImportJob`` تازه می‌سازد و فایلِ CSV را در ذخیره‌سازیِ خصوصی
    می‌نویسد — نگاه کنید به ADR-62. هرگز چیزی از فایل نمی‌خواند/پردازش
    نمی‌کند (آن کارِ ``run_preview``ست)."""
    if import_type not in ImportJob.ImportType.values:
        raise ImportServiceError(f"نوعِ واردات «{import_type}» نامعتبر است.")
    if mode not in ImportJob.Mode.values:
        raise ImportServiceError(f"حالتِ «{mode}» نامعتبر است.")
    validate_csv_upload(uploaded_file)
    if idempotency_key and ImportJob.objects.filter(store=store, idempotency_key=idempotency_key).exists():
        raise ImportServiceError("این کلیدِ یکتا قبلاً برایِ یک واردات دیگر استفاده شده است.")

    job = ImportJob.objects.create(
        store=store, import_type=import_type, original_filename=(uploaded_file.name or "")[:255],
        status=ImportJob.Status.UPLOADED, requested_by=requested_by, mode=mode,
        dry_run=True, idempotency_key=idempotency_key,
    )
    job.source_file.save(f"{import_type}-{job.pk}.csv", uploaded_file, save=True)
    record_audit_event(
        store=store, actor=requested_by, action_code="import.uploaded",
        object_type="ImportJob", object_id=str(job.pk), object_label=job.original_filename,
        metadata={"import_type": import_type, "mode": mode},
    )
    return job


def read_job_rows(job: ImportJob) -> list[dict]:
    """محتوایِ فایلِ منبعِ Job را به فهرستی از دیکشنری‌هایِ نرمال‌شده تبدیل
    می‌کند — همان تابعِ ``read_csv_rows_bounded`` که آپلود/پیش‌نمایش/اجرا هر
    سه از آن استفاده می‌کنند (بدونِ منطقِ موازیِ دوم)."""
    job.source_file.open("rb")
    try:
        return list(read_csv_rows_bounded(job.source_file))
    finally:
        job.source_file.close()


def run_preview(job: ImportJob, *, actor) -> ImportJob:
    """پیش‌نمایشِ (dry-run) یک Job — هرگز چیزی در دیتابیسِ کاتالوگ/موجودی
    نمی‌نویسد؛ فقط ``ImportRowResult``هایِ پیش‌نمایش را می‌سازد."""
    if job.status not in (ImportJob.Status.UPLOADED, ImportJob.Status.PREVIEW_READY):
        raise ImportServiceError("این Job دیگر قابلِ پیش‌نمایش نیست.")
    job.dry_run = True
    rows = read_job_rows(job)
    return run_import(job, rows, actor=actor)


def run_execution(job: ImportJob, *, actor) -> ImportJob:
    """اجرایِ واقعیِ یک Job — نگاه کنید به ADR-61: یک Jobِ قبلاً
    تکمیل‌شده (هر یک از ``ImportJob.FINAL_STATUSES``) هرگز دوباره اجرا
    نمی‌شود، حتی اگر این تابع دوباره صدا زده شود (idempotent replay-safe)."""
    if job.status in ImportJob.FINAL_STATUSES:
        raise ImportServiceError("این Job قبلاً به پایان رسیده — دوباره اجرا نمی‌شود.")
    job.dry_run = False
    rows = read_job_rows(job)
    return run_import(job, rows, actor=actor)
