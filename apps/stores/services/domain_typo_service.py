"""تشخیصِ اشتباهِ تایپیِ محتملِ نامِ دامنه — فقط پیشنهاد، هرگز اصلاحِ خودکار
(هیچ تابعی در این ماژول مقدارِ واردشده را تغییر نمی‌دهد، فقط یک پیشنهاد
برمی‌گرداند که خودِ مرچنت باید تأیید/رد کند).

دو دسته بررسی می‌شود، هر دو بدونِ نیاز به یک پایگاه‌داده‌ی خارجیِ «دامنه‌های
واقعی» (که این کدبیس ندارد و اختراعش گمراه‌کننده بود):

۱. شباهتِ نزدیک به یکی از دامنه‌های اختصاصیِ همین Store که از قبل ثبت شده
   (سناریویِ رایج: تایپِ دوباره‌ی همان دامنه با یک اشتباهِ کوچک).
۲. اشتباهِ تایپیِ رایج در خودِ TLD نسبت به فهرستِ کوچکی از TLDهای متداول
   (مثلِ ``.cm`` به‌جایِ ``.com``، ``.ri`` به‌جایِ ``.ir``)."""

import difflib

COMMON_TLDS = (
    "ir", "com", "org", "net", "co", "info", "shop", "store",
    "co.ir", "org.ir", "net.ir", "ac.ir", "gov.ir", "id.ir",
)

#: شباهتِ کمینه برایِ این‌که دو رشته «به‌احتمالِ زیاد همان یکی با یک
#: اشتباهِ تایپی» در نظر گرفته شوند — نه دو دامنه‌ی واقعاً متفاوت.
_SIMILARITY_CUTOFF = 0.82


def suggest_similar_existing_domain(*, store, hostname: str) -> str | None:
    """اگر ``hostname`` بسیار شبیهِ (اما نه دقیقاً برابرِ) یکی از دامنه‌های
    اختصاصیِ از‌قبل‌ثبت‌شده‌ی همین Store باشد، آن دامنه را برمی‌گرداند —
    سناریوی رایج: تایپِ دوباره‌ی دامنه‌ای که قبلاً اضافه کرده با یک حرفِ
    اضافه/جاافتاده. در غیرِ این صورت ``None``."""
    from apps.stores.models import StoreDomain

    existing = list(
        StoreDomain.objects.filter(
            store=store, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
        ).exclude(hostname=hostname).values_list("hostname", flat=True)
    )
    if not existing:
        return None
    matches = difflib.get_close_matches(hostname, existing, n=1, cutoff=_SIMILARITY_CUTOFF)
    return matches[0] if matches else None


def _levenshtein(a: str, b: str) -> int:
    """فاصله‌ی ویرایشیِ Damerau-Levenshtein (نسخه‌ی optimal-string-alignment) —
    برایِ رشته‌های کوتاهِ TLD قابل‌اعتمادتر از نسبتِ
    ``difflib.SequenceMatcher`` است (آن نسبت برایِ رشته‌های ۲-۳ حرفی رفتارِ
    غیرِشهودی می‌دهد). جابه‌جاییِ دو حرفِ مجاور (مثلِ ``ri``/``ir``) هم یک
    ویرایشِ واحد حساب می‌شود — دقیقاً همان اشتباهِ تایپیِ رایج."""
    if a == b:
        return 0
    previous_row = list(range(len(b) + 1))
    two_rows_back = None
    for i, char_a in enumerate(a, start=1):
        current_row = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            value = min(
                previous_row[j] + 1,        # حذف
                current_row[j - 1] + 1,     # درج
                previous_row[j - 1] + cost,  # جایگزینی
            )
            if (
                two_rows_back is not None and i > 1 and j > 1
                and char_a == b[j - 2] and a[i - 2] == char_b
            ):
                value = min(value, two_rows_back[j - 2] + 1)  # جابه‌جاییِ دو حرفِ مجاور
            current_row.append(value)
        two_rows_back = previous_row
        previous_row = current_row
    return previous_row[-1]


#: بیشینه‌ی فاصله‌ی ویرایشیِ قابل‌قبول برایِ «اشتباهِ تایپیِ محتملِ TLD» —
#: بزرگ‌تر از این یعنی احتمالاً TLDای کاملاً متفاوت و عمداً است، نه تایپو.
_TLD_MAX_EDIT_DISTANCE = 1


def suggest_tld_correction(hostname: str) -> str | None:
    """اگر TLD واردشده به یکی از TLDهای متداول بسیار نزدیک (اما نه دقیقاً
    برابر) باشد، نسخه‌ی اصلاح‌شده‌ی کاملِ دامنه را پیشنهاد می‌دهد — مثلاً
    ``shop.cm`` → ``shop.com``. اگر خودِ TLD از قبل دقیقاً یکی از فهرستِ
    متداول‌هاست، یا هیچ پیشنهادِ نزدیکی نیست، ``None``."""
    if "." not in hostname:
        return None
    base, _, tld = hostname.rpartition(".")
    if not base or tld in COMMON_TLDS:
        return None
    best_tld, best_distance = None, _TLD_MAX_EDIT_DISTANCE + 1
    for candidate in COMMON_TLDS:
        distance = _levenshtein(tld, candidate)
        if distance < best_distance:
            best_tld, best_distance = candidate, distance
    if best_tld is None or best_distance > _TLD_MAX_EDIT_DISTANCE:
        return None
    return f"{base}.{best_tld}"


def suggest_domain_typo(*, store, hostname: str) -> str | None:
    """یک پیشنهادِ واحد (اگر باشد) — اول شباهت به دامنه‌ی موجودِ همین
    Store، سپس اصلاحِ محتملِ TLD. هرگز چیزی را جایگزین نمی‌کند، فقط
    برمی‌گرداند تا view/template به‌صورتِ «آیا منظورتان X بود؟» نشان دهد."""
    return suggest_similar_existing_domain(store=store, hostname=hostname) or suggest_tld_correction(hostname)
