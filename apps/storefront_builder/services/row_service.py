"""اعتبارسنجیِ ترکیبِ چند section در یک «ردیف» — Phase 1 (معماریِ Universal
Block/Data)، بخشِ ۵.۲ مشخصات: «۱/۲/۳/۴ ستون در یک ردیف».

معماریِ انتخاب‌شده عمداً یک مدلِ جداگانه (``GridRow``) نیست — طبقِ الزامِ صریحِ
کار («Do NOT assume a new GridRow database model is required... choose the
simplest architecture that satisfies the specification»). به‌جایِ آن، دو فیلدِ
سبک روی خودِ ``StorefrontSection`` (``row_key``/``row_span`` — ``models.py``)
گروه‌بندی را نمایندگی می‌کنند:

- ``row_key`` خالی = section مستقل، عرضِ کامل (رفتارِ فعلی، بدونِ تغییر — اکثریتِ
  قریب‌به‌اتفاقِ sectionهای موجود).
- ``row_key`` غیرخالی = این section عضوِ یک ردیفِ ترکیبی است؛ همه‌ی sectionهایی
  که دقیقاً همین مقدار را دارند (در همان صفحه)، اعضایِ همان ردیف‌اند.
- ``row_span`` (پیش‌فرض ۱۲) فقط برایِ اعضایِ یک ردیف معنا دارد — یک گریدِ
  ۱۲-واحدیِ استاندارد (دقیقاً همان قراردادی که Bootstrap/CSS گریدِ موجودِ این
  پروژه از قبل استفاده می‌کند)، پس ۲ ستونِ مساوی=۶+۶، ۳ ستونِ مساوی=۴+۴+۴، ۴
  ستونِ مساوی=۳+۳+۳+۳، و عرضِ نامساوی مثلِ یک‌سوم+دو‌سوم (Hero+Instant Offer در
  V5) = ۴+۸.

چرا این طراحی به‌جایِ یک مدلِ ردیفِ جدا:

- بدونِ جدولِ اضافه/بدونِ سطحِ تودرتویِ جدید در دیتامدل — هر section هنوز
  مستقیماً زیرِ ``StorefrontPage`` است (دقیقاً همان معماریِ Phase 1A).
  Drag & Drop هنوز فقط رویِ همان فهرستِ تخت با ``order`` کار می‌کند؛ عضویتِ
  ردیف فقط یک متادیتایِ اضافی روی هر ردیف است، نه یک سلسله‌مراتبِ جدید.
- Migration کاملاً افزایشی و امن است (نگاه کنید به ``0012_...``): هر
  ۳ فیلدِ جدید یک پیش‌فرضِ ساده دارند که دقیقاً معادلِ رفتارِ امروز است — هیچ
  دادهٔ موجودی نیاز به backfill/تفسیرِ دوباره ندارد.
- اعتبارسنجی (این ماژول) کاملاً جدا از رندر است — دقیقاً همان تفکیکِ
  مسئولیتی که section_registry/section_data_service دارند.

این ماژول فقط لایه‌یِ اعتبارسنجی/سرویس است — **رندرِ واقعیِ یک ردیف به HTML
(Phase 2: Universal Renderer) هنوز اینجا نیست.** ``render_service.group_items_into_rows``
یک تبدیلِ دادهٔ خالص (نه رندرِ template) است که همین قراردادِ ``row_key``/
``row_span`` را مصرف می‌کند — نگاه کنید به docstring آن تابع.
"""

from __future__ import annotations

#: طبقِ بخشِ ۵.۲ مشخصات: «۱ ستون / ۲ ستون / ۳ ستون / ۴ ستون». یک section
#: مستقل (row_key خالی) معادلِ «۱ ستون» است و اصلاً از این ماژول عبور
#: نمی‌کند؛ پس این ماژول فقط ترکیب‌های واقعیِ ۲ تا ۴ عضو را اعتبارسنجی می‌کند.
MIN_ROW_MEMBERS = 2
MAX_ROW_MEMBERS = 4

#: گریدِ ۱۲-واحدی — مجموعِ row_span اعضایِ یک ردیف باید دقیقاً این عدد شود.
ROW_WIDTH_UNITS = 12


class RowAssignmentError(ValueError):
    """ترکیبِ فعلیِ row_key/row_span رویِ یک صفحه نامعتبر است — پیامِ فارسیِ
    قابل‌نمایشِ مستقیم به تاجر."""


def _grouped_by_row_key(ordered_sections) -> list[tuple[str, list]]:
    """sectionهایِ فعال/غیرفعالِ یک صفحه را، به همان ترتیبِ ``order`` که پاس
    داده شده، به گروه‌هایِ «اجراهایِ پیوسته» (contiguous runs) با همان
    row_key تقسیم می‌کند. یک ``row_key`` غیرخالی که در دو نقطه‌ی غیرمجاورِ
    فهرست ظاهر شود (یعنی section دیگری با row_key متفاوت بینِ آن‌ها آمده)
    عمداً دو گروهِ *جدا* حساب می‌شود — نه یک گروهِ واحد — چون از دیدِ
    بصری/رندر دیگر یک ردیفِ واحد نیستند؛ ``validate_page_row_layout`` این
    حالت را به‌عنوانِ خطایِ «ردیفِ ناپیوسته» رد می‌کند (نه اینکه بی‌صدا آن‌ها
    را یکی حساب کند)."""
    groups: list[tuple[str, list]] = []
    for section in ordered_sections:
        key = section.row_key or ""
        if groups and groups[-1][0] == key and key != "":
            groups[-1][1].append(section)
        else:
            groups.append((key, [section]))
    return groups


def validate_page_row_layout(ordered_sections) -> None:
    """ترکیبِ row_key/row_span همه‌یِ sectionهایِ **یک صفحه** (به ترتیبِ
    ``order``) را اعتبارسنجی می‌کند — fail-closed، یک ``RowAssignmentError``
    با اولین نقضِ یافت‌شده.

    این تابع را هر مسیرِ سرویس/ویویی که row_key/row_span را می‌نویسد (Phase
    ۲ به بعد — این تابع خودش هیچ‌جا در Phase 1 خودکار صدا زده نمی‌شود، فقط
    قراردادِ اعتبارسنجی را تعریف/تست می‌کند) باید پیش از ذخیره صدا بزند.

    قوانین:
    - هر گروهِ row_key غیرخالی باید بینِ ``MIN_ROW_MEMBERS`` تا
      ``MAX_ROW_MEMBERS`` عضو داشته باشد (بخشِ ۵.۲ مشخصات: حداکثر ۴ ستون).
    - اعضایِ یک row_key باید در فهرستِ مرتب‌شده **پیوسته** باشند (بدونِ
      section دیگری بینِ آن‌ها) — وگرنه دیگر از نظرِ بصری یک ردیفِ واحد
      نیستند.
    - مجموعِ ``row_span`` اعضایِ یک گروه باید دقیقاً برابرِ
      ``ROW_WIDTH_UNITS`` (۱۲) باشد.
    - ``row_span`` هر عضو باید بینِ ۱ تا ۱۲ باشد.
    - sectionهایِ بدونِ row_key (اکثریت) اصلاً بررسی نمی‌شوند.
    """
    for row_key, members in _grouped_by_row_key(list(ordered_sections)):
        if not row_key:
            continue
        if len(members) < MIN_ROW_MEMBERS:
            raise RowAssignmentError(
                f"ردیف «{row_key}» فقط یک عضوِ پیوسته دارد — یک ردیفِ ترکیبی باید "
                f"حداقل {MIN_ROW_MEMBERS} بخش داشته باشد (یا row_key را خالی بگذارید)."
            )
        if len(members) > MAX_ROW_MEMBERS:
            raise RowAssignmentError(
                f"ردیف «{row_key}» {len(members)} عضو دارد — حداکثرِ مجاز "
                f"{MAX_ROW_MEMBERS} بخش در یک ردیف است."
            )
        for section in members:
            if not (1 <= section.row_span <= ROW_WIDTH_UNITS):
                raise RowAssignmentError(
                    f"عرضِ بخش «{section.section_key}» در ردیف «{row_key}» نامعتبر است "
                    f"— باید بینِ ۱ تا {ROW_WIDTH_UNITS} باشد."
                )
        total_span = sum(section.row_span for section in members)
        if total_span != ROW_WIDTH_UNITS:
            raise RowAssignmentError(
                f"مجموعِ عرضِ اعضایِ ردیف «{row_key}» باید دقیقاً {ROW_WIDTH_UNITS} باشد "
                f"— مقدارِ فعلی: {total_span}."
            )


def is_row_member(section) -> bool:
    """میان‌بُرِ خوانا برایِ «آیا این section عضوِ یک ردیفِ ترکیبی است؟» —
    معادلِ ``bool(section.row_key)``، جایی که مصرف‌کننده نباید مستقیماً به
    شکلِ خامِ فیلد (رشته‌یِ خالی در برابرِ None) وابسته باشد."""
    return bool(section.row_key)
