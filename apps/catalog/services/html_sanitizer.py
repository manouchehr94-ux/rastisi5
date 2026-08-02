"""پاک‌سازیِ HTMLِ توضیحاتِ کالا — خروجیِ ویرایشگرِ متنِ غنی (CKEditor5) هرگز
مستقیماً ذخیره نمی‌شود؛ همیشه باید از ``sanitize_product_description`` عبور
کند.

از ``BeautifulSoup`` استفاده می‌کند (وابستگیِ از پیش موجودِ پروژه —
``beautifulsoup4`` در requirements.txt) به‌جایِ افزودنِ کتابخانه‌ی جدید
(bleach/nh3). یک allowlist سخت‌گیرانه از تگ‌ها/ویژگی‌ها/خواصِ style: تگ‌های
خطرناک (script، iframe، object، embed، style، form...) و ویژگی‌های
event-handler (onclick و مانند آن) و لینک‌های ``javascript:`` همیشه حذف
می‌شوند، حتی اگر در allowlist اشتباهاً قرار گیرند.
"""

from bs4 import BeautifulSoup, NavigableString

ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4",
    "strong", "b", "em", "i", "u", "s", "sub", "sup",
    "ul", "ol", "li", "a", "blockquote", "span", "div",
    "table", "thead", "tbody", "tr", "th", "td", "img", "figure", "figcaption",
}

ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "span": {"style"},
    "div": {"style"},
    "p": {"style"},
    "td": {"style", "colspan", "rowspan"},
    "th": {"style", "colspan", "rowspan"},
    "table": {"style"},
    "*": set(),
}

#: خواصِ CSS مجاز درونِ ویژگیِ style — همان امکاناتِ نوارِ ابزارِ ویرایشگر
#: (فونت، اندازه، رنگ، تراز، ضخامت، زیرخط) و نه چیزِ دیگری (بدونِ position/
#: url()/behavior که می‌توانند برایِ حملات CSS استفاده شوند).
ALLOWED_STYLE_PROPS = {
    "color", "background-color", "font-family", "font-size", "font-weight",
    "text-align", "text-decoration", "font-style",
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto", "tel"}


def _clean_style(value: str) -> str:
    declarations = []
    for part in value.split(";"):
        if ":" not in part:
            continue
        prop, _, val = part.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if prop in ALLOWED_STYLE_PROPS and val and "url(" not in val.lower() and "expression(" not in val.lower():
            declarations.append(f"{prop}: {val}")
    return "; ".join(declarations)


def _is_safe_url(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    if url.startswith("#") or url.startswith("/"):
        return True
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    return scheme in ALLOWED_URL_SCHEMES


def sanitize_product_description(raw_html: str) -> str:
    """خروجیِ HTMLِ ویرایشگر را با allowlist پاک‌سازی می‌کند و رشته‌ی امن برمی‌گرداند."""
    if not raw_html or not raw_html.strip():
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")

    # تگ‌های کاملاً غیرمجاز باید *پیش از* پاسِ unwrap زیر حذف شوند (با
    # محتوایشان، نه فقط unwrap) — وگرنه مثلاً متنِ داخلِ <script> به‌عنوانِ
    # متنِ ساده روی صفحه باقی می‌ماند.
    for tag in soup.find_all(["script", "style", "iframe", "object", "embed", "form", "input", "button", "svg"]):
        tag.decompose()

    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()
            continue

        allowed_for_tag = ALLOWED_ATTRS.get(tag.name, set()) | ALLOWED_ATTRS["*"]
        for attr_name in list(tag.attrs.keys()):
            if attr_name.lower().startswith("on"):
                del tag.attrs[attr_name]
                continue
            if attr_name not in allowed_for_tag:
                del tag.attrs[attr_name]
                continue
            if attr_name == "style":
                cleaned = _clean_style(tag.attrs[attr_name])
                if cleaned:
                    tag.attrs[attr_name] = cleaned
                else:
                    del tag.attrs[attr_name]
            elif attr_name in {"href", "src"}:
                if not _is_safe_url(tag.attrs[attr_name]):
                    del tag.attrs[attr_name]
            elif attr_name == "target":
                if tag.attrs[attr_name] == "_blank":
                    tag.attrs["rel"] = "noopener noreferrer"
                else:
                    del tag.attrs[attr_name]

    return str(soup).strip()


_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "ul", "ol", "table", "blockquote", "figure"}


def render_description_html(raw_html: str) -> str:
    """پاک‌سازی + آماده‌سازی برایِ نمایش در فروشگاه — امنِ رندرِ مستقیم (``|safe``).

    توضیحاتِ قدیمی (پیش از افزودنِ ویرایشگرِ متنِ غنی) متنِ ساده با خط‌های
    جدید بودند، نه HTML — اگر خروجیِ پاک‌سازی‌شده هیچ تگِ بلاکی نداشته باشد
    (یعنی دقیقاً همین حالت)، خط‌های جدید به ``<br>`` تبدیل می‌شوند تا رفتارِ
    قبلیِ فیلترِ ``linebreaks`` حفظ شود — کالاهای موجود بدونِ تغییرِ ظاهری
    باقی می‌مانند."""
    cleaned = sanitize_product_description(raw_html)
    if not cleaned:
        return ""
    soup = BeautifulSoup(cleaned, "html.parser")
    has_block = any(getattr(child, "name", None) in _BLOCK_TAGS for child in soup.children)
    if has_block:
        return cleaned
    return cleaned.replace("\r\n", "\n").replace("\n", "<br>")


def strip_to_text(raw_html: str, *, max_length: int = 300) -> str:
    """برایِ خلاصه/پیش‌نمایشِ متنیِ ساده (بدونِ تگ) — مثلاً پیش‌نمایشِ سئو."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = " ".join(
        chunk.strip() for chunk in soup.stripped_strings if isinstance(chunk, str) or isinstance(chunk, NavigableString)
    )
    text = " ".join(text.split())
    return text[:max_length]
