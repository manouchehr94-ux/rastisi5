"""موتورِ محاسبه‌ی مالیات — نگاه کنید به ADR-44 (دامنه‌ی تنظیماتِ مالیات)،
ADR-45 (تطبیق نرخ و بازگشت به رفتارِ قدیمی)، ADR-46 (سیاستِ گردکردن) در
``SAAS_DOMAIN_DECISIONS.md``.

Rastisi مالیات را طبقِ قواعدِ پیکربندی‌شده‌ی مدیرِ فروشگاه محاسبه می‌کند و
هیچ مشاوره‌ی حقوقی/مالیاتی‌ای ارائه نمی‌دهد — این پیام در UI پنل مدیریتِ
مالیات هم به‌صراحت نمایش داده می‌شود.

سازگاریِ پیش‌رونده: وقتی هیچ ``TaxRate``ای برای یک Store ثبت نشده باشد
(وضعیتِ هر Storeِ موجود پیش از این چک‌پوینت)، محاسبه دقیقاً به فرمولِ
قدیمیِ ``cart_totals`` بازمی‌گردد: یک نرخِ ثابتِ درصدی
(``ShopSettings.tax_percent``) روی مبلغِ پس‌از-تخفیف، گردشده یک‌باره روی
مجموع — بدونِ کوچک‌ترین اختلافِ عددی."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.core.models import ShopSettings
from apps.orders.models import TaxRate


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def store_has_granular_tax_rates(store) -> bool:
    """آیا این Store حداقل یک ``TaxRate`` ثبت کرده — تعیین‌کننده‌ی این‌که
    مسیرِ «قدیمی/تخت» یا مسیرِ «دانه‌ریز/دسته‌ی مالیاتی» اجرا شود."""
    return TaxRate.objects.filter(store=store).exists()


def resolve_tax_rate(store, *, tax_class=None, province: str = "") -> TaxRate | None:
    """نرخِ برنده را طبقِ ADR-45 برمی‌گرداند: تطبیقِ دقیقِ استان > سراسریِ
    Store (``province=""``) > هیچ تطبیقی. اگر ``tax_class`` داده نشده باشد
    (کالا دسته‌ی مالیاتیِ اختصاصی ندارد)، دسته‌ی پیش‌فرضِ Store استفاده
    می‌شود؛ اگر آن هم وجود نداشته باشد، ``None`` برمی‌گردد."""
    if tax_class is None:
        settings_row = ShopSettings.load(store=store)
        tax_class = settings_row.default_tax_class
    if tax_class is None:
        return None

    now = timezone.now()
    candidates = [
        rate for rate in TaxRate.objects.filter(store=store, tax_class=tax_class, is_active=True)
        if (rate.start_at is None or rate.start_at <= now) and (rate.end_at is None or rate.end_at >= now)
    ]
    if not candidates:
        return None

    exact = [r for r in candidates if province and r.province == province]
    if exact:
        return sorted(exact, key=lambda r: (r.priority, r.pk))[0]

    store_wide = [r for r in candidates if r.province == ""]
    if store_wide:
        return sorted(store_wide, key=lambda r: (r.priority, r.pk))[0]

    return None


def calculate_order_taxes(store, *, items, shipping_amount: Decimal, province: str = "") -> dict:
    """مالیاتِ کاملِ یک سبد/سفارش را محاسبه می‌کند.

    ``items``: لیستی از dict با کلیدهای ``unit_price``، ``quantity``،
    ``discount_allocation`` (پیش‌فرض صفر)، ``tax_class`` (اختیاری).

    خروجی: dict شامل ``lines`` (لیستِ نتیجه‌ی هر ردیف)، ``line_tax_total``،
    ``shipping_tax``، ``total_tax``، ``prices_include_tax``،
    ``tax_rounding_policy``.
    """
    settings_row = ShopSettings.load(store=store)

    if not settings_row.tax_enabled:
        lines = [
            {
                "item_ref": item.get("item_ref"), "unit_price": item["unit_price"], "quantity": item["quantity"],
                "taxable_amount": Decimal("0"), "tax_class_code": "", "tax_class_name": "",
                "tax_rate_percent": None, "unit_tax": Decimal("0"), "total_tax": Decimal("0"),
            }
            for item in items
        ]
        return {
            "lines": lines, "line_tax_total": Decimal("0"), "shipping_tax": Decimal("0"),
            "total_tax": Decimal("0"), "prices_include_tax": settings_row.prices_include_tax,
            "tax_added_to_grand_total": Decimal("0"),
            "tax_rounding_policy": settings_row.tax_rounding_policy,
        }

    if not store_has_granular_tax_rates(store):
        return _legacy_flat_tax(items, shipping_amount=shipping_amount, settings_row=settings_row)

    return _granular_tax(store, items=items, shipping_amount=shipping_amount, province=province, settings_row=settings_row)


def _extract_or_add_tax(line_subtotal: Decimal, tax_percent: Decimal, *, inclusive: bool) -> Decimal:
    """مالیاتِ یک ردیف را حساب می‌کند — نگاه کنید به ADR-45.

    ``inclusive=False`` (پیش‌فرض، رفتارِ همیشگیِ این کدبیس پیش از این
    چک‌پوینت): مالیات جدا و روی مبلغ افزوده می‌شود
    (``line_subtotal × rate / 100``).

    ``inclusive=True``: ``line_subtotal`` از قبل شاملِ مالیات است، پس
    مالیات از دلِ همان مبلغ استخراج می‌شود
    (``line_subtotal × rate / (100 + rate)``) — نه افزوده به آن."""
    if inclusive:
        return _round(line_subtotal * tax_percent / (Decimal("100") + tax_percent)) if tax_percent else Decimal("0")
    return _round(line_subtotal * tax_percent / Decimal("100"))


def _legacy_flat_tax(items, *, shipping_amount: Decimal, settings_row: ShopSettings) -> dict:
    """مسیرِ قدیمی — دقیقاً همان فرمولِ ``cart_totals`` پیش از این چک‌پوینت
    وقتی ``prices_include_tax=False`` (پیش‌فرض و تنها حالتِ هر Storeِ
    موجود): یک نرخِ ثابتِ درصدی روی جمعِ کل، گردشده یک‌باره، افزوده به
    grand_total. تفکیکِ ردیفی فقط برای نمایش است."""
    tax_percent = settings_row.tax_percent
    inclusive = settings_row.prices_include_tax
    taxable_total = Decimal("0")
    lines = []
    for item in items:
        line_subtotal = item["unit_price"] * item["quantity"] - item.get("discount_allocation", Decimal("0"))
        taxable_total += line_subtotal
        lines.append({
            "item_ref": item.get("item_ref"),
            "unit_price": item["unit_price"], "quantity": item["quantity"],
            "taxable_amount": line_subtotal, "tax_class_code": "", "tax_class_name": "",
            "tax_rate_percent": tax_percent, "unit_tax": None, "total_tax": None,
        })

    total_tax = _extract_or_add_tax(taxable_total, tax_percent, inclusive=inclusive)

    # سهمِ هر ردیف از مالیاتِ کل فقط برای نمایش تخصیص می‌یابد (تناسبی)، بدون
    # این‌که جمعشان لزوماً دقیقاً با total_tax برابر باشد وقتی گردکردنِ
    # per_line رخ می‌داد — این‌جا رخ نمی‌دهد چون سیاست on_total است.
    for line in lines:
        if taxable_total > 0:
            line["total_tax"] = _extract_or_add_tax(line["taxable_amount"], tax_percent, inclusive=inclusive)
            if inclusive:
                line["taxable_amount"] = line["taxable_amount"] - line["total_tax"]
        else:
            line["total_tax"] = Decimal("0")
        line["unit_tax"] = (
            _round(line["total_tax"] / line["quantity"]) if line["quantity"] else Decimal("0")
        )

    shipping_tax = (
        _round(shipping_amount * tax_percent / Decimal("100")) if settings_row.shipping_taxable else Decimal("0")
    )

    return {
        "lines": lines, "line_tax_total": total_tax, "shipping_tax": shipping_tax,
        "total_tax": total_tax + shipping_tax, "prices_include_tax": inclusive,
        # مالیاتِ کالا وقتی inclusive است از قبل داخلِ items_total نشسته —
        # نباید دوباره روی grand_total افزوده شود؛ مالیاتِ ارسال همیشه
        # جداگانه و افزودنی می‌ماند (ADR-45: ارسال همیشه exclusive قیمت‌گذاری
        # می‌شود، مستقل از تنظیمِ قیمتِ کالاها).
        "tax_added_to_grand_total": (Decimal("0") if inclusive else total_tax) + shipping_tax,
        "tax_rounding_policy": settings_row.tax_rounding_policy,
    }


def _granular_tax(store, *, items, shipping_amount: Decimal, province: str, settings_row: ShopSettings) -> dict:
    """مسیرِ دانه‌ریز — هر ردیف دسته‌ی مالیاتیِ خودش (یا پیش‌فرضِ Store) را
    حل می‌کند؛ اگر هیچ نرخی برای آن دسته/استان تطبیق نداشته باشد، مالیاتِ
    آن ردیف صفر است (نه بازگشتِ خاموش به نرخِ تخت — نگاه کنید به ADR-45:
    وقتی Store حداقل یک TaxRate دارد، یعنی صراحتاً حالتِ «دانه‌ریز» را
    انتخاب کرده و پوششِ ناقص باید آشکار بماند، نه پنهان‌شده پشتِ نرخِ تخت)."""
    per_line = settings_row.tax_rounding_policy == ShopSettings.TaxRoundingPolicy.PER_LINE
    inclusive = settings_row.prices_include_tax
    lines = []
    running_taxable = Decimal("0")
    running_tax = Decimal("0")

    for item in items:
        line_subtotal = item["unit_price"] * item["quantity"] - item.get("discount_allocation", Decimal("0"))
        tax_class = item.get("tax_class")
        rate = resolve_tax_rate(store, tax_class=tax_class, province=province)
        rate_percent = rate.rate_percent if rate is not None else Decimal("0")
        raw_line_tax = _extract_or_add_tax(line_subtotal, rate_percent, inclusive=inclusive)
        line_tax = raw_line_tax if per_line else (
            line_subtotal * rate_percent / (Decimal("100") + rate_percent) if inclusive and rate_percent
            else line_subtotal * rate_percent / Decimal("100") if not inclusive
            else Decimal("0")
        )

        running_taxable += line_subtotal
        running_tax += line_tax

        taxable_amount = line_subtotal - raw_line_tax if inclusive else line_subtotal
        lines.append({
            "item_ref": item.get("item_ref"),
            "unit_price": item["unit_price"], "quantity": item["quantity"],
            "taxable_amount": taxable_amount,
            "tax_class_code": tax_class.code if tax_class else "",
            "tax_class_name": tax_class.name if tax_class else "",
            "tax_rate_percent": rate_percent if rate is not None else None,
            "total_tax": raw_line_tax if per_line else _round(line_tax),
            "unit_tax": (
                _round((raw_line_tax if per_line else _round(line_tax)) / item["quantity"])
                if item["quantity"] else Decimal("0")
            ),
        })

    line_tax_total = running_tax if per_line else _round(running_tax)

    applicable_shipping_rate = Decimal("0")
    if settings_row.shipping_taxable:
        default_rate = resolve_tax_rate(store, tax_class=settings_row.default_tax_class, province=province)
        if default_rate is not None:
            applicable_shipping_rate = default_rate.rate_percent
    # هزینه‌ی ارسال همیشه exclusive قیمت‌گذاری می‌شود (ADR-45)، مستقل از
    # این‌که قیمتِ کالاها inclusive باشد یا نه.
    shipping_tax = _round(shipping_amount * applicable_shipping_rate / Decimal("100"))

    return {
        "lines": lines, "line_tax_total": line_tax_total, "shipping_tax": shipping_tax,
        "total_tax": line_tax_total + shipping_tax, "prices_include_tax": inclusive,
        "tax_added_to_grand_total": (Decimal("0") if inclusive else line_tax_total) + shipping_tax,
        "tax_rounding_policy": settings_row.tax_rounding_policy,
    }
