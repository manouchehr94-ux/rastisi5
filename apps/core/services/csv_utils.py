"""ابزارهای CSV مشترکِ صادرات/واردات — نگاه کنید به ADR-51 (امنیتِ CSV) و
ADR-62 (فایل‌هایِ واردات) در ``SAAS_DOMAIN_DECISIONS.md``.

سیاستِ این ماژول تنها منبعِ سازگاریِ کدگذاری/محافظتِ تزریق برای هر فایلِ
CSVای است که این کدبیس تولید یا می‌خواند — هیچ ویو یا سرویسی نباید
``csv.writer``/``csv.reader`` را مستقیماً و بدونِ عبور از این توابع
فراخوانی کند."""

import csv
import io
from decimal import Decimal, InvalidOperation

from apps.core.utils import normalize_digits

#: محدودیت‌های آپلودِ فایلِ واردات (checkpoint 4B) — مقادیرِ ثابت و مستند،
#: نه قابل‌تنظیم از بیرون؛ نگاه کنید به ADR-62 برایِ توجیه.
MAX_IMPORT_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 مگابایت
MAX_IMPORT_ROWS = 20_000
MAX_FIELD_LENGTH = 2_000
ALLOWED_IMPORT_CONTENT_TYPES = frozenset({"text/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"})
ALLOWED_IMPORT_EXTENSIONS = frozenset({".csv"})


class CsvUploadError(Exception):
    """فایلِ آپلودشده رد شد — پیامِ آن برای نمایشِ مستقیم به کاربر امن است."""


class CsvRowLimitExceededError(Exception):
    """تعدادِ ردیف‌هایِ فایل از ``MAX_IMPORT_ROWS`` بیشتر است."""

# کاراکترهایی که نرم‌افزارهای صفحه‌گسترده (اکسل/گوگل‌شیت) در ابتدای یک
# سلول را به‌عنوانِ آغازِ یک فرمول تفسیر می‌کنند — نگاه کنید به OWASP CSV
# Injection. مقداری که با هرکدام از این‌ها شروع شود، پیش از نوشتن با یک
# آپاستروفِ تکی (``'``) پیشوند می‌شود؛ این هم مقدار را برای انسان قابل‌خواندن
# نگه می‌دارد و هم از تفسیرِ آن به‌عنوانِ فرمول توسطِ صفحه‌گستر جلوگیری
# می‌کند.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def sanitize_csv_cell(value) -> str:
    """مقدارِ خام را برای نوشتنِ امن در یک سلولِ CSV آماده می‌کند — نگاه کنید
    به ADR-51. ``None`` به رشته‌ی خالی تبدیل می‌شود؛ مقادیرِ غیررشته‌ای
    (Decimal/int/datetime/...) به ``str()`` تبدیل می‌شوند."""
    if value is None:
        text = ""
    else:
        text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def write_csv_rows(fileobj, *, header: list, rows) -> int:
    """هدر و ردیف‌ها را با پاک‌سازیِ هر سلول (``sanitize_csv_cell``) در
    ``fileobj`` می‌نویسد — UTF-8، بدونِ BOM (این کدبیس فقط برای مصرفِ
    داخلی/بین سیستمی طراحی شده، نه لزوماً بازشدن مستقیم در اکسلِ ویندوزی؛
    اگر لازم شد BOM را می‌توان بعداً به‌صورتِ گزینه اضافه کرد). تعدادِ
    ردیف‌های نوشته‌شده (بدونِ هدر) را برمی‌گرداند."""
    writer = csv.writer(fileobj)
    writer.writerow([sanitize_csv_cell(cell) for cell in header])
    count = 0
    for row in rows:
        writer.writerow([sanitize_csv_cell(cell) for cell in row])
        count += 1
    return count


def read_csv_rows(fileobj):
    """فایلِ CSV را به‌صورتِ ``csv.DictReader`` می‌خواند — UTF-8 با
    نادیده‌گرفتنِ BOM (اگر فایل با اکسل ساخته شده باشد). کلیدهای هدر
    strip می‌شوند تا فاصله‌ی تصادفی در نامِ ستون رد نشود."""
    wrapper = io.TextIOWrapper(fileobj, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(wrapper)
    if reader.fieldnames:
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
    yield from reader


def validate_csv_upload(uploaded_file) -> None:
    """بررسیِ امنیتیِ یک فایلِ آپلودشده پیش از هرگونه پردازش — نگاه کنید به
    ADR-62. هرگز به نامِ فایل/پسوند/Content-Type به‌تنهایی اعتماد نمی‌کند
    (این‌ها همه client-controlled هستند)، اما همه را به‌عنوانِ یک لایه‌ی
    دفاعیِ اول رد می‌کند — لایه‌ی واقعی، خودِ ``csv.DictReader`` است که
    هرگز چیزی جز متن را اجرا/تفسیر نمی‌کند (بدون فرمول/HTML/اسکریپت).

    ``CsvUploadError`` را با پیامِ قابل‌نمایش می‌اندازد؛ چیزی برنمی‌گرداند."""
    name = getattr(uploaded_file, "name", "") or ""
    # نامِ فایل هرگز مستقیماً برایِ مسیرِ دیسک استفاده نمی‌شود (نگاه کنید به
    # ``import_job_upload_path`` در apps/core/models.py) — این بررسی فقط
    # پسوندِ نمایشی/دسته‌بندیِ نوعِ فایل است، نه یک گامِ امنیتیِ مسیر.
    lowered = name.lower()
    if not any(lowered.endswith(ext) for ext in ALLOWED_IMPORT_EXTENSIONS):
        raise CsvUploadError("فقط فایلِ CSV پذیرفته می‌شود.")
    if "/" in name or "\\" in name or "\x00" in name:
        raise CsvUploadError("نامِ فایل نامعتبر است.")

    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_IMPORT_FILE_SIZE_BYTES:
        raise CsvUploadError(
            f"حجمِ فایل نباید بیشتر از {MAX_IMPORT_FILE_SIZE_BYTES // (1024 * 1024)} مگابایت باشد."
        )

    content_type = getattr(uploaded_file, "content_type", "") or ""
    if content_type and content_type not in ALLOWED_IMPORT_CONTENT_TYPES:
        raise CsvUploadError(f"نوعِ فایلِ «{content_type}» پذیرفته نمی‌شود.")


def read_csv_rows_bounded(fileobj, *, max_rows: int = MAX_IMPORT_ROWS, max_field_length: int = MAX_FIELD_LENGTH):
    """مثلِ ``read_csv_rows`` — به‌علاوه‌ی محدودیتِ تعدادِ ردیف و طولِ هر
    سلول، و بی‌سروصدا حذفِ کاراکترِ null-byte (که هم اکسل و هم بعضی
    ابزارهایِ صادرات گاهی به‌اشتباه در سلولِ خالی می‌گذارند) — هرگز کلِ
    فایل را در حافظه بارگذاری نمی‌کند (ژنراتور، خطِ به خط)."""
    count = 0
    try:
        for row in read_csv_rows(fileobj):
            count += 1
            if count > max_rows:
                raise CsvRowLimitExceededError(f"تعدادِ ردیف‌ها از حداکثرِ مجاز ({max_rows}) بیشتر است.")
            cleaned = {}
            for key, value in row.items():
                if value is None:
                    cleaned[key] = value
                    continue
                text = value.replace("\x00", "")
                if len(text) > max_field_length:
                    text = text[:max_field_length]
                cleaned[key] = text
            yield cleaned
    except UnicodeDecodeError:
        raise CsvUploadError("فایل با کدگذاریِ UTF-8 معتبر نیست.")


def normalize_import_text(value) -> str:
    """رشته‌ی ورودیِ یک سلولِ CSV را برای پردازش آماده می‌کند — ارقامِ
    فارسی/عربی را لاتین می‌کند و فاصله‌هایِ ابتدا/انتها را حذف می‌کند.
    ``None`` به رشته‌ی خالی تبدیل می‌شود."""
    if value is None:
        return ""
    return normalize_digits(str(value)).strip()


def parse_import_decimal(value, *, field_name: str = "مقدار"):
    """رشته‌ی یک سلول را (پس از نرمال‌سازیِ ارقامِ فارسی/عربی) به ``Decimal``
    ایمن تبدیل می‌کند. رشته‌ی خالی ``None`` برمی‌گرداند (یعنی «مقدار داده
    نشده»، نه صفر). مقدارِ نامعتبر ``ValueError`` با پیامِ قابل‌نمایش
    می‌اندازد."""
    text = normalize_import_text(value)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"«{value}» یک عددِ اعشاریِ معتبر برایِ {field_name} نیست.")


def parse_import_int(value, *, field_name: str = "مقدار"):
    """مثلِ ``parse_import_decimal`` اما برایِ عددِ صحیح (مثلاً موجودی)."""
    text = normalize_import_text(value)
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        raise ValueError(f"«{value}» یک عددِ صحیحِ معتبر برایِ {field_name} نیست.")


_TRUE_VALUES = {"true", "1", "yes", "y", "بله", "فعال", "درست", "on"}
_FALSE_VALUES = {"false", "0", "no", "n", "خیر", "غیرفعال", "نادرست", "off"}


def parse_import_bool(value, *, default: bool | None = None):
    """مقدارِ بولیِ یک سلول را از رویِ مجموعه‌ای از نمایش‌هایِ رایج (فارسی/
    انگلیسی) تشخیص می‌دهد. رشته‌ی خالی، اگر ``default`` داده شده باشد همان
    را برمی‌گرداند؛ در غیرِ این صورت ``ValueError`` می‌اندازد."""
    text = normalize_import_text(value).lower()
    if not text:
        if default is not None:
            return default
        raise ValueError("مقدارِ بولی خالی است.")
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ValueError(f"«{value}» یک مقدارِ بولیِ قابل‌تشخیص نیست.")
