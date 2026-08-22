"""Variant Contract — U1A: Engine Metadata Contract Foundation.

این ماژول **یک Registry رقیب/دوم نیست** — ``section_registry.SECTION_REGISTRY``
تنها نگاشتِ ثابتِ مجاز برای resolve کردنِ ``section_key`` باقی می‌ماند
(دقیقاً همان تعهدِ صریحِ R1: «SECTION_REGISTRY remains the single
authoritative section registry»). این ماژول فقط شکلِ داده‌ایِ یک
«Variant» را تعریف می‌کند که ``SectionDefinition`` می‌تواند اختیاراً
حمل کند (فیلدِ ``variants``، در ``section_registry.py``) — دقیقاً مثلِ
اینکه ``validate_settings`` یک تابع است، نه یک نوعِ جدید از section.

طبقِ الزامِ صریحِ کارِ U1A، دو الگویِ ساختاریِ مجاز باید هر دو پشتیبانی
شوند:

الگویِ A — همان renderer/template + تنظیمات/توکنِ متفاوت
    (نمونه‌یِ اثبات‌شده: ``category_grid``/``brand_carousel``/
    ``product_section`` — هر سه یک ``template_name`` دارند و فقط با
    شاخه‌زنیِ CSS/HTML رویِ یک کلیدِ enum بسته [``display_mode``]
    ظاهرِ متفاوت می‌سازند).

الگویِ B — یک renderer partial ثبت‌شده‌یِ متفاوت برایِ DOM واقعاً متفاوت
    (``VariantDefinition.renderer`` اختیاری — اگر غایب باشد، renderer
    خودِ ``SectionDefinition`` استفاده می‌شود؛ اگر حاضر باشد، فقط یک
    رشته‌یِ ثابتِ نوشته‌شده توسطِ کدِ Python همین Registry است، هرگز از
    JSONِ ذخیره‌شده/ورودیِ مرچنت خوانده نمی‌شود — نگاه کنید به
    ``_validate_variant_renderer`` پایین).

هیچ شاخه‌زنیِ ``template_key``/``store.slug``/``family_slug`` در این
ماژول یا هیچ مصرف‌کننده‌ای از آن مجاز نیست — تفاوتِ ساختاری همیشه به
Variant تعلق دارد (یک نوعِ Componentِ عمومی)، هرگز به یک فروشگاه/Template
مشخص.

**دامنه‌یِ U1A** (طبقِ برنامه‌یِ فاز): فقط قراردادِ داده + کمک‌تابع‌هایِ
resolve/اعتبارسنجیِ خالص. هیچ رندری اینجا اتفاق نمی‌افتد، هیچ کوئریِ
دیتابیسی زده نمی‌شود، و ``render_service`` در این فاز به این ماژول
سیم‌کشی نمی‌شود — پیوندِ واقعیِ رندر یک تصمیمِ فازِ بعدی است."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping as _MappingABC
from types import MappingProxyType
from typing import Callable, Mapping


class InvalidVariantDefinitionError(ValueError):
    """یک ``VariantDefinition`` ساخته‌شده در کدِ Registry (نه ورودیِ مرچنت)
    شکلِ نامعتبر دارد — همیشه در زمانِ import رخ می‌دهد، هرگز در زمانِ
    اجرا برایِ یک مرچنتِ واقعی (همان فلسفه‌یِ
    ``layout_preset_registry.InvalidLayoutPresetError``)."""


def _freeze_metadata(value):
    """External-review correction (U1A final pass, item 2) — the earlier
    ``MappingProxyType(dict(...))`` hardening only protected the *outer*
    mapping; a nested ``dict``/``list`` inside ``responsive_defaults``/
    ``motion_defaults`` was still an ordinary mutable object reachable
    through it. Recursively normalize common JSON-like metadata shapes into
    genuinely immutable equivalents, at every depth:

    - ``Mapping`` → ``MappingProxyType`` of recursively frozen values.
    - ``list``/``tuple`` → ``tuple`` of recursively frozen values.
    - ``set``/``frozenset`` → ``frozenset`` of recursively frozen values.
    - anything else (str/int/float/bool/None/...) → returned unchanged,
      already immutable.

    Deliberately five plain ``isinstance`` branches, not a generic
    serialization/rules engine — this only ever needs to handle the shapes
    that already exist in ``StorefrontSection.settings``-style JSON."""
    if isinstance(value, _MappingABC):
        return MappingProxyType({key: _freeze_metadata(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_metadata(item) for item in value)
    return value


def _thaw_metadata(value):
    """Inverse of ``_freeze_metadata`` — used only by the public resolvers
    (``resolve_responsive_defaults``/``resolve_motion_defaults``) to hand
    callers an ordinary, independently-mutable copy. Mutating the returned
    structure (at any depth) can never reach back into the frozen
    ``VariantDefinition`` this value came from, because every container
    along the way is rebuilt fresh here rather than referenced."""
    if isinstance(value, _MappingABC):
        return {key: _thaw_metadata(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_metadata(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw_metadata(item) for item in value}
    return value


@dataclasses.dataclass(frozen=True)
class VariantDefinition:
    """یک متغیّرِ ثبت‌شده‌یِ یک ``SectionDefinition`` — قراردادِ داده‌ایِ
    خالص، بدونِ هیچ رفتارِ رندر/دیتابیسی. هر فیلد اختیاری/دارایِ
    پیش‌فرضِ امن است به‌جز ``key``/``label_fa`` — همان الگویِ
    ``SectionDefinition`` خودش."""

    key: str
    label_fa: str
    #: نامِ Templateِ Django برایِ این Variant — **اختیاری**. اگر ``None``
    #: باشد، ``resolve_renderer_template`` نامِ Templateِ خودِ
    #: ``SectionDefinition`` (الگویِ A) را برمی‌گرداند. اگر حاضر باشد،
    #: باید مستقیماً در کدِ پایتونِ همین ماژول/فایل‌هایِ Registry نوشته
    #: شده باشد (الگویِ B) — هرگز از تنظیماتِ ذخیره‌شده/ورودیِ مرچنت.
    renderer: str | None = None
    #: تابعِ اعتبارسنجی/پیش‌فرضِ اختصاصیِ این Variant — اختیاری. غیابِ
    #: آن یعنی این Variant هیچ شکلِ تنظیماتِ اضافه‌ای نسبت به
    #: ``SectionDefinition.validate_settings``/``default_settings`` خودش
    #: اضافه نمی‌کند (رفتارِ فعلیِ سه نمونه‌یِ اثبات‌شده دقیقاً همین است —
    #: enum انتخابِ Variant از قبل توسطِ اعتبارسنجِ خودِ section چک
    #: می‌شود).
    validate_settings: Callable[[dict], dict] | None = None
    default_settings: Callable[[], dict] | None = None
    capabilities: frozenset[str] = frozenset()
    supported_settings: frozenset[str] | None = None
    required_data: frozenset[str] = frozenset()
    #: Override اختیاریِ بلوکِ ``responsive``/``motion`` — ``None`` یعنی
    #: «همان پیش‌فرضِ سطحِ section را بدونِ تغییر استفاده کن» (نگاه کنید
    #: به ``resolve_responsive_defaults``/``resolve_motion_defaults``).
    responsive_defaults: Mapping | None = None
    motion_defaults: Mapping | None = None

    def __post_init__(self) -> None:
        """External-review correction (U1A pre-commit pass, item 1) —
        ``frozen=True`` only stops *reassigning* an attribute; it does
        nothing to stop a caller passing a mutable ``set``/``list``/``dict``
        into a field the contract treats as immutable, nor does it stop
        that same mutable object being mutated *after* construction while
        still referenced by this (already-constructed) definition.

        Normalize every collection-typed field to a genuinely immutable
        value at construction time, using ``object.__setattr__`` (the
        standard, explicit way to touch a field from inside a frozen
        dataclass's own ``__post_init__`` — not a generic rules engine, just
        five direct, targeted coercions):

        - ``capabilities``/``required_data`` → always a ``frozenset`` (never
          the caller's original ``set``/``list`` object).
        - ``supported_settings`` → ``None`` stays exactly ``None`` (never
          coerced away — see ``resolve_supported_settings``'s
          None-vs-empty-frozenset contract); any other value becomes a
          ``frozenset``.
        - ``responsive_defaults``/``motion_defaults`` → ``None`` stays
          ``None``; any other mapping is recursively frozen via
          ``_freeze_metadata`` (U1A final correction, item 2 — a *deep*
          freeze, not just the outer ``MappingProxyType``: a nested
          ``dict``/``list`` inside one of these fields is frozen too, so
          e.g. ``variant.responsive_defaults["mobile"]["columns"] = 99``
          raises ``TypeError`` rather than silently mutating the stored
          definition). Neither the caller's original object nor anything
          nested inside it can be mutated later through this definition.
          Resolvers (``resolve_responsive_defaults``/``resolve_motion_defaults``)
          call ``_thaw_metadata`` to hand their own callers back an
          ordinary, independently-mutable copy — that part of the public
          API is unchanged; only the *stored* value on the definition
          itself is hardened, at every depth.
        """
        object.__setattr__(self, "capabilities", frozenset(self.capabilities or ()))
        object.__setattr__(self, "required_data", frozenset(self.required_data or ()))
        if self.supported_settings is not None:
            object.__setattr__(self, "supported_settings", frozenset(self.supported_settings))
        if self.responsive_defaults is not None:
            object.__setattr__(self, "responsive_defaults", _freeze_metadata(self.responsive_defaults))
        if self.motion_defaults is not None:
            object.__setattr__(self, "motion_defaults", _freeze_metadata(self.motion_defaults))


#: External-review correction (U1A pre-commit pass, item 3) — a
#: ``SectionDefinition`` variant's renderer, if present, must live in the
#: same trusted local namespace as every ``SectionDefinition.template_name``
#: already in ``SECTION_REGISTRY`` (see every entry in
#: ``_BASE_SECTION_REGISTRY``: all 34 use exactly this prefix). Constraining
#: the *namespace*, not just rejecting individual bad characters, is what
#: keeps this a closed allowlist rather than a denylist that only catches
#: attack shapes someone already thought of.
SECTION_VARIANT_RENDERER_NAMESPACE = "storefront_builder/sections/"

#: A leading Windows drive letter (``C:\...`` or ``C:/...``) — irrelevant to
#: a Django template loader, but rejected explicitly so a renderer string
#: can never be mistaken for (or copy-pasted from) a filesystem path.
_WINDOWS_DRIVE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_variant_renderer(renderer: str | None) -> None:
    """بررسیِ شکلیِ renderer — ``None`` (الگویِ A) همیشه معتبر است. اگر
    حاضر باشد، باید دقیقاً یک مسیرِ محلیِ قابل‌اعتماد در فضای نامِ
    section templates (``SECTION_VARIANT_RENDERER_NAMESPACE``) باشد — هیچ
    مسیرِ مطلق، UNC، بک‌اسلش، درایوِ ویندوزی، ``..``، یا رشته‌ی خالی
    پذیرفته نمی‌شود. این تنها یک لایه‌یِ دفاعِ *اضافه* است؛ ایمنیِ واقعی
    از اینجا می‌آید که ``renderer`` هرگز از JSONِ ذخیره‌شده/ورودیِ مرچنت
    resolve نمی‌شود — همیشه رشته‌ای ثابت است که در کدِ پایتونِ همین
    Registry نوشته شده (بدونِ import پویا/eval). وجودِ خودِ Templateِ
    مقصد (filesystem/Django loader) عمداً اینجا چک نمی‌شود — طبقِ الزامِ
    صریحِ کار، این ماژول در فازِ U1A هیچ رندری انجام نمی‌دهد."""
    if renderer is None:
        return
    if not isinstance(renderer, str) or not renderer.strip():
        raise InvalidVariantDefinitionError("renderer باید یک رشته‌ی غیرخالی یا None باشد")
    if renderer != renderer.strip():
        raise InvalidVariantDefinitionError(f"renderer «{renderer}» نباید فاصله‌ی ابتدا/انتهایی داشته باشد")
    if "\\" in renderer:
        raise InvalidVariantDefinitionError(f"renderer «{renderer}» نباید شامل بک‌اسلش باشد")
    if renderer.startswith("/"):
        raise InvalidVariantDefinitionError(f"renderer «{renderer}» نباید مسیرِ مطلق باشد")
    if _WINDOWS_DRIVE_PATH_RE.match(renderer):
        raise InvalidVariantDefinitionError(f"renderer «{renderer}» نباید مسیرِ درایوِ ویندوزی باشد")
    if ".." in renderer:
        raise InvalidVariantDefinitionError(f"renderer «{renderer}» نباید شامل .. باشد")
    if not renderer.startswith(SECTION_VARIANT_RENDERER_NAMESPACE):
        raise InvalidVariantDefinitionError(
            f"renderer «{renderer}» باید در فضای نامِ section templates باشد "
            f"(«{SECTION_VARIANT_RENDERER_NAMESPACE}»)"
        )


def validate_variant_definition(variant: VariantDefinition) -> None:
    """اعتبارسنجیِ شکلِ یک ``VariantDefinition`` — فقط در زمانِ import
    برایِ Variantهایِ درون‌ساختِ Registry فراخوانی می‌شود (نه در مسیرِ
    درخواستِ یک مرچنت)."""
    if not isinstance(variant.key, str) or not variant.key.strip():
        raise InvalidVariantDefinitionError("کلیدِ Variant نمی‌تواند خالی باشد")
    if not isinstance(variant.label_fa, str) or not variant.label_fa.strip():
        raise InvalidVariantDefinitionError(f"برچسبِ Variant «{variant.key}» نمی‌تواند خالی باشد")
    _validate_variant_renderer(variant.renderer)


def validate_variants(variants: tuple[VariantDefinition, ...], *, default_variant: str | None) -> None:
    """اعتبارسنجیِ کلِ فهرستِ Variantهایِ یک ``SectionDefinition`` —
    کلیدهایِ تکراری رد می‌شوند، ``default_variant`` (اگر داده شده) باید
    به یکی از همین کلیدها اشاره کند. فهرستِ خالی همیشه معتبر است (یعنی
    «این section هنوز هیچ Variantی ندارد» — رفتارِ امنِ پیش‌فرضِ ۳۱ نوعِ
    باقی‌مانده‌یِ SECTION_REGISTRY)."""
    seen: set[str] = set()
    for variant in variants:
        validate_variant_definition(variant)
        if variant.key in seen:
            raise InvalidVariantDefinitionError(f"کلیدِ Variant «{variant.key}» تکراری است")
        seen.add(variant.key)
    if default_variant is not None and default_variant not in seen:
        raise InvalidVariantDefinitionError(
            f"default_variant «{default_variant}» به هیچ Variantِ ثبت‌شده‌ای اشاره نمی‌کند"
        )


# --------------------------------------------------------------- resolve

def list_variants(definition) -> tuple[VariantDefinition, ...]:
    """فهرستِ Variantهایِ یک ``SectionDefinition`` — فهرستِ خالی برایِ
    تعریف‌هایی که هنوز هیچ Variantی ندارند (رفتارِ امنِ پیش‌فرض)."""
    return tuple(getattr(definition, "variants", ()) or ())


def get_variant(definition, variant_key: str | None) -> VariantDefinition | None:
    """جست‌وجویِ یک Variant با کلید — ``None`` برایِ کلیدِ غایب/نامعتبر
    (بدونِ پرتابِ خطا؛ فراخوان مسئولِ تصمیمِ fallback است)."""
    if not variant_key:
        return None
    for variant in list_variants(definition):
        if variant.key == variant_key:
            return variant
    return None


def resolve_active_variant(definition, settings: dict | None) -> VariantDefinition | None:
    """Variantِ فعال را از رویِ ``settings`` ذخیره‌شده resolve می‌کند —
    تابعِ خالص/بدونِ کوئری/بدونِ شاخه‌زنیِ tenant/template.

    قرارداد (طبقِ الزامِ کارِ U1A):

    - تعریفِ بدونِ Variant → همیشه ``None`` (fallback امن).
    - کلیدِ persisted شده که Variant را انتخاب می‌کند از
      ``definition.variant_setting_key`` خوانده می‌شود (پیش‌فرض
      ``"variant"`` اگر تنظیم نشده باشد) — این دقیقاً همان مکانیزمی است
      که به سه نمونه‌ی اثبات‌شده (``display_mode``) اجازه می‌دهد بدونِ
      rename شدنِ کلیدِ ذخیره‌شده در سیستمِ عمومیِ Variant شرکت کنند.
    - مقدارِ غایب/نامعتبر هرگز خطا پرتاب نمی‌کند — بی‌صدا به
      ``default_variant`` برمی‌گردد (اگر ثبت شده و resolve شود)، وگرنه
      ``None``. این «شکستِ ایمن» است، نه ساختنِ fallbackِ site-specific."""
    variants = list_variants(definition)
    if not variants:
        return None

    settings = settings if isinstance(settings, dict) else {}
    setting_key = getattr(definition, "variant_setting_key", None) or "variant"
    requested = settings.get(setting_key)

    match = get_variant(definition, requested)
    if match is not None:
        return match

    default_key = getattr(definition, "default_variant", None)
    return get_variant(definition, default_key)


class UnknownVariantSelectionError(ValueError):
    """U1B1 §5 (write-time validation) — a newly-submitted settings value
    names a variant key that is not registered for this
    ``SectionDefinition``. Deliberately never raised at *read* time —
    ``resolve_active_variant`` above is the read-time path and always fails
    safely to ``default_variant`` instead, per its own contract; this
    exception exists only for the write path that submits a brand-new
    ``StorefrontSection.settings`` value."""


def validate_variant_selection(definition, cleaned_settings: dict) -> None:
    """اعتبارسنجیِ زمانِ نوشتن (نه رندر) برایِ کلیدِ انتخاب‌کننده‌یِ
    Variant — پس از عبورِ کاملِ ``cleaned_settings`` از
    ``validate_settings`` خودِ section (شاملِ هر enum بسته‌ای که خودش از
    قبل اجرا می‌کند). مقدارِ غایب/خالی هرگز خطا نیست (fallback به
    ``default_variant`` کارِ زمانِ رندر است، نه زمانِ نوشتن — نگاه کنید
    به ``resolve_active_variant``). فقط یک مقدارِ *حاضر و غیرِخالی* که به
    هیچ ``VariantDefinition`` ثبت‌شده‌ای اشاره نکند رد می‌شود.

    برایِ سه نمونه‌ی اثبات‌شده (``category_grid``/``brand_carousel``/
    ``product_section``) این تابع در عمل هرگز خطا پرتاب نمی‌کند — چون
    ``validate_settings`` خودِ آن‌ها از قبل مقدارِ نامعتبر را به یک
    مقدارِ مجاز coerce کرده (نگاه کنید به ``_validate_category_grid_settings``
    و مشابه‌هایش) پیش از رسیدن به اینجا؛ این تابع برایِ آن‌ها صرفاً یک
    شبکه‌ی ایمنیِ بی‌اثر است، نه یک قاعده‌ی متضاد یا تکراری. برایِ یک
    section آینده که خودش چنین enum بسته‌ای اجرا نمی‌کند، این تابع
    قراردادِ عمومیِ U1B1 را واقعاً اجرا می‌کند."""
    variants = list_variants(definition)
    if not variants:
        return
    if not isinstance(cleaned_settings, dict):
        return
    setting_key = getattr(definition, "variant_setting_key", None) or "variant"
    value = cleaned_settings.get(setting_key)
    if not value:
        return
    if get_variant(definition, value) is None:
        raise UnknownVariantSelectionError(
            f"مقدارِ «{value}» برایِ «{setting_key}» در «{definition.key}» به هیچ "
            f"Variantِ ثبت‌شده‌ای اشاره نمی‌کند"
        )


def resolve_capabilities(definition, variant: VariantDefinition | None = None) -> frozenset[str]:
    """اجتماعِ capabilities سطحِ section و (اگر داده شده) سطحِ Variant."""
    base = frozenset(getattr(definition, "capabilities", frozenset()) or frozenset())
    if variant is None:
        return base
    return base | frozenset(variant.capabilities or frozenset())


def resolve_supported_settings(definition, variant: VariantDefinition | None = None) -> frozenset[str] | None:
    """``supported_settings`` سطحِ Variant (اگر صراحتاً تنظیم شده باشد)
    جایگزینِ سطحِ section می‌شود؛ وگرنه سطحِ section برمی‌گردد (که خودش
    می‌تواند ``None`` باشد — یعنی «همه‌ی تنظیماتِ موجود پشتیبانی
    می‌شوند»، رفتارِ پیش‌فرضِ فعلی)."""
    if variant is not None and variant.supported_settings is not None:
        return frozenset(variant.supported_settings)
    section_level = getattr(definition, "supported_settings", None)
    return frozenset(section_level) if section_level is not None else None


def resolve_required_data(definition, variant: VariantDefinition | None = None) -> frozenset[str]:
    base = frozenset(getattr(definition, "required_data", frozenset()) or frozenset())
    if variant is None:
        return base
    return base | frozenset(variant.required_data or frozenset())


def resolve_renderer_template(definition, variant: VariantDefinition | None = None) -> str:
    """نامِ Templateِ فعال — الگویِ B (اگر ``variant.renderer`` تنظیم شده)
    یا الگویِ A (پیش‌فرض: همان ``definition.template_name``). این تابع
    **رندر نمی‌کند** — فقط رشته‌ی نامِ Template را resolve می‌کند؛
    استفاده‌ی واقعیِ آن در ``render_service`` عمداً خارج از دامنه‌ی U1A
    است (نگاه کنید به docstring بالای فایل)."""
    if variant is not None and variant.renderer:
        return variant.renderer
    return definition.template_name


def resolve_responsive_defaults(definition, variant: VariantDefinition | None = None) -> dict:
    """پیش‌فرضِ بلوکِ ``responsive`` — از رویِ همان منبعِ حقیقتِ موجود
    (``definition.default_settings()["responsive"]``، که توسطِ
    ``_with_responsive`` برایِ **همه‌ی** انواع، بدونِ استثنا، تزریق
    می‌شود) خوانده می‌شود، نه یک کپیِ جداگانه — پس هرگز نمی‌تواند از
    رفتارِ واقعیِ رندر منحرف/desync شود. اگر Variant صراحتاً override
    داشته باشد، همان override برمی‌گردد. اگر override از رویِ Variant
    بیاید، ``_thaw_metadata`` یک کپیِ کاملاً مستقل و قابل‌تغییر برمی‌گرداند
    (U1A final correction، بندِ ۲) — تغییرِ نتیجه، حتی در عمقِ تودرتو،
    هرگز نمی‌تواند به ``VariantDefinition`` ذخیره‌شده برگردد."""
    if variant is not None and variant.responsive_defaults is not None:
        return _thaw_metadata(variant.responsive_defaults)
    defaults = definition.default_settings() or {}
    responsive = defaults.get("responsive")
    return dict(responsive) if isinstance(responsive, dict) else {}


def resolve_motion_defaults(definition, variant: VariantDefinition | None = None) -> dict | None:
    """پیش‌فرضِ بلوکِ ``motion`` — فقط برایِ انواعِ ``MOTION_AWARE`` مقدار
    دارد (بقیه ``None``، چون اصلاً بلوکِ motion در ``default_settings()``
    آن‌ها تزریق نمی‌شود — رفتارِ فعلیِ بدونِ تغییر). همانِ ``_thaw_metadata``
    برایِ overrideِ سطحِ Variant اعمال می‌شود — نگاه کنید به
    ``resolve_responsive_defaults`` بالا."""
    if variant is not None and variant.motion_defaults is not None:
        return _thaw_metadata(variant.motion_defaults)
    defaults = definition.default_settings() or {}
    motion = defaults.get("motion")
    return dict(motion) if isinstance(motion, dict) else None


# ------------------------------------------------ config schema convention

#: نسخه‌یِ قراردادِ JSONِ موتور — طبقِ بخشِ ۱۲ کارِ U1A: فقط یک قراردادِ
#: کمینه/افزایشی برایِ فازِ بعدی (U7: Template key/version/baseline).
#: **هیچ Storeی در U1A این کلیدها را ننوشته/نمی‌گیرد** — این فقط شکلِ
#: توافق‌شده است، نه یک فیلدِ در حالِ استفاده.
ENGINE_SCHEMA_VERSION = 1

#: External-review correction (U1A pre-commit pass, item 6) — the closed
#: set of ``schema_version`` values this build of the engine actually
#: understands. A future/unrecognized version (e.g. a store written by a
#: later engine build) must never be silently treated as "known compatible"
#: just because it happens to parse as an int — see
#: ``UnsupportedEngineSchemaVersionError`` below.
SUPPORTED_ENGINE_SCHEMA_VERSIONS: frozenset[int] = frozenset({ENGINE_SCHEMA_VERSION})


class UnsupportedEngineSchemaVersionError(ValueError):
    """An explicitly-present ``schema_version`` is not in
    ``SUPPORTED_ENGINE_SCHEMA_VERSIONS`` (or is not a valid integer at all).
    Raised deliberately, rather than silently falling back to the current
    version — a future engine build must be able to tell "this Draft/Version
    predates a breaking provenance-shape change" apart from "this Draft/
    Version simply never wrote provenance yet" (the latter is the *missing*
    case, handled separately by ``validate_template_provenance`` returning
    the neutral default)."""


def build_template_provenance(
    *, template_key: str | None = None, template_version: str | None = None,
) -> dict:
    """شکلِ کمینه/افزایشیِ قراردادِ provenance — فقط یک سازنده‌یِ دیکشنری
    برایِ فازِ U7 (Template key/version/baseline)، بدونِ نوشتنِ آن در
    هیچ Store/Draftِ واقعی در همین فاز."""
    return {
        "engine": {"schema_version": ENGINE_SCHEMA_VERSION},
        "template": {"key": template_key, "version": template_version},
    }


def validate_template_provenance(raw: dict | None) -> dict:
    """اعتبارسنجیِ شکلیِ قراردادِ provenance. **در U1A از هیچ مسیرِ
    اجرایی‌ای فراخوانی نمی‌شود** — فقط برایِ اثباتِ قراردادِ آینده در
    تست موجود است.

    دو حالت را عمداً متفاوت رفتار می‌کند (اصلاحِ بازبینیِ خارجی، بندِ ۶):

    - **غایب** (کلاً ``raw`` غیرِdict/None است، یا ``engine``/``schema_version``
      اصلاً نوشته نشده — یعنی «داده‌یِ قدیمیِ ازپیش‌موجود که هرگز از این
      قرارداد عبور نکرده») → بی‌صدا به شکلِ خنثیِ فعلی (``ENGINE_SCHEMA_VERSION``)
      بازمی‌گردد، نه خطا — دقیقاً همان تسامحِ ``validate_responsive_settings``.
    - **حاضر اما نامعتبر/پشتیبانی‌نشده** (مثلاً ``schema_version=999``، یا
      هر مقداری که یک ``int`` واقعیِ پایتون نباشد) →
      ``UnsupportedEngineSchemaVersionError`` پرتاب می‌شود، هرگز بی‌صدا به
      نسخه‌ی فعلی سقوط نمی‌کند — این دقیقاً تفاوتِ «هنوز provenance
      ننوشته» با «provenanceِ نسخه‌ای که این build نمی‌شناسد» است.

    U1A final correction (بندِ ۱) — نوع‌بندیِ سخت‌گیرانه: ``schema_version``
    باید دقیقاً ``type(x) is int`` باشد، نه صرفاً چیزی که با ``int(x)``
    قابلِ تبدیل است. این عمداً موارد زیر را رد می‌کند، نه می‌پذیرد:
    ``True``/``False`` (که ``bool`` هستند، زیرکلاسِ ``int``، اما
    ``type(True) is int`` نادرست است)، ``1.0``/``1.9`` (``float``)،
    ``"1"``/``"01"`` (``str``)، و ``None``. یک قراردادِ سازگاریِ نسخه که
    ``"1"``/``1.0``/``True`` را بی‌صدا هم‌ارزِ ``1`` بگیرد، در آینده دقیقاً
    همان دسته از باگِ خاموش را باز می‌کند که این قرارداد از اول برایِ
    جلوگیری از آن نوشته شده."""
    if not isinstance(raw, dict):
        return build_template_provenance()

    engine = raw.get("engine") if isinstance(raw.get("engine"), dict) else {}
    template = raw.get("template") if isinstance(raw.get("template"), dict) else {}

    if "schema_version" in engine:
        raw_version = engine["schema_version"]
        if type(raw_version) is not int:
            raise UnsupportedEngineSchemaVersionError(
                f"schema_version «{raw_version!r}» باید یک عددِ صحیحِ Python (int) باشد، "
                f"نه {type(raw_version).__name__}"
            )
        schema_version = raw_version
        if schema_version not in SUPPORTED_ENGINE_SCHEMA_VERSIONS:
            raise UnsupportedEngineSchemaVersionError(
                f"schema_version {schema_version} توسطِ این نسخه از موتور پشتیبانی نمی‌شود "
                f"(نسخه‌های پشتیبانی‌شده: {sorted(SUPPORTED_ENGINE_SCHEMA_VERSIONS)})"
            )
    else:
        schema_version = ENGINE_SCHEMA_VERSION

    template_key = template.get("key")
    template_version = template.get("version")
    return {
        "engine": {"schema_version": schema_version},
        "template": {
            "key": template_key if isinstance(template_key, str) else None,
            "version": template_version if isinstance(template_version, str) else None,
        },
    }
