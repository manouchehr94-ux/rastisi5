"""ابزارهای CSV مشترکِ صادرات/واردات — نگاه کنید به ADR-51 (امنیتِ CSV) در
``SAAS_DOMAIN_DECISIONS.md``.

سیاستِ این ماژول تنها منبعِ سازگاریِ کدگذاری/محافظتِ تزریق برای هر فایلِ
CSVای است که این کدبیس تولید یا می‌خواند — هیچ ویو یا سرویسی نباید
``csv.writer``/``csv.reader`` را مستقیماً و بدونِ عبور از این توابع
فراخوانی کند."""

import csv
import io

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
