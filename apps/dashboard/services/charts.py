"""ساخت نمودارهای SVG سرور-رندر برای داشبورد پنل مدیریت — بدون هیچ کتابخانه‌ی جاوااسکریپتی.

منطق دقیقاً معادل توابع lineChart/donut در docs/spec/shop-admin-panel.html است
تا وفاداری بصری کامل حفظ شود، فقط اینجا در پایتون و با داده‌ی واقعی دیتابیس.
"""

from apps.core.utils import format_toman, to_fa_digits


def build_line_chart_svg(data: list, labels: list[str], color: str = "#4f46e5") -> str:
    """نمودار خطی روند فروش را می‌سازد؛ data مقادیر تومانی و labels برچسب محور افقی است."""
    width, height, pad_l, pad_r, pad_t, pad_b = 640, 250, 14, 14, 16, 30
    values = [float(v) for v in data] or [0]
    n = len(values)
    max_v = max(values) * 1.15 if max(values) > 0 else 1
    min_v = 0

    def xs(i):
        return pad_l + i * (width - pad_l - pad_r) / (n - 1) if n > 1 else pad_l

    def ys(v):
        return pad_t + (height - pad_t - pad_b) * (1 - (v - min_v) / (max_v - min_v))

    points = [(xs(i), ys(v)) for i, v in enumerate(values)]
    line = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(points))
    area = f"{line} L {xs(n - 1):.1f} {height - pad_b} L {xs(0):.1f} {height - pad_b} Z"

    grid = ""
    for t in (0, 0.25, 0.5, 0.75, 1):
        y = pad_t + (height - pad_t - pad_b) * t
        val = round(max_v * (1 - t))
        grid += (
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'stroke="var(--border)" stroke-dasharray="4 4"/>'
            f'<text x="{width - pad_r}" y="{y - 4:.1f}" font-size="9" fill="var(--muted)" '
            f'text-anchor="end">{format_toman(val, with_unit=False)}</text>'
        )

    step = max(1, -(-n // 10)) if n > 14 else 1
    lbls = ""
    for i, label in enumerate(labels):
        if n > 14 and i % step != 0:
            continue
        lbls += (
            f'<text x="{xs(i):.1f}" y="{height - 10}" font-size="9.5" fill="var(--muted)" '
            f'text-anchor="middle">{label}</text>'
        )

    dots = ""
    for i, (x, y) in enumerate(points):
        title = f"{labels[i]}: {format_toman(values[i])}" if i < len(labels) else format_toman(values[i])
        dots += (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="var(--card)" stroke="{color}" '
            f'stroke-width="2"><title>{title}</title></circle>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" style="width:100%;height:auto;font-family:inherit">'
        f'<defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity=".28"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
        f'{grid}<path d="{area}" fill="url(#lg)"/>'
        f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>{dots}{lbls}</svg>'
    )


def build_donut_chart_svg(items: list[dict]) -> str:
    """نمودار دایره‌ای وضعیت سفارش‌ها؛ هر آیتم: {"label", "value", "color"}."""
    total = sum(item["value"] for item in items)
    radius = 62
    circumference = 2 * 3.14159265358979 * radius
    offset = 0
    segments = ""
    for item in items:
        frac = (item["value"] / total) if total else 0
        dash = frac * circumference
        segments += (
            f'<circle cx="80" cy="80" r="{radius}" fill="none" stroke="{item["color"]}" stroke-width="20" '
            f'stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 80 80)"><title>{item["label"]}: {to_fa_digits(item["value"])} '
            f'({to_fa_digits(round(frac * 100))}٪)</title></circle>'
        )
        offset += dash

    return (
        f'<svg viewBox="0 0 160 160" style="width:165px;height:165px">{segments}'
        f'<text x="80" y="76" text-anchor="middle" font-size="21" font-weight="800" '
        f'fill="var(--text)">{to_fa_digits(total)}</text>'
        f'<text x="80" y="95" text-anchor="middle" font-size="10" fill="var(--muted)">سفارش</text></svg>'
    )
