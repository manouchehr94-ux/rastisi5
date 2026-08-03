# گزارش ممیزی معماری: سازنده بصری صفحه فروشگاه (Visual Storefront Page Builder)

**فاز:** ممیزی (Phase 1) — فقط بررسی و گزارش، بدون تغییر رفتار برنامه.

**شاخه:** `claude/rastisi-storefront-builder-audit`
**کامیت پایه:** `72b1034` — "Rebuild industry catalog: 100 approved industries + Other, unified selector"
**تاریخ:** 2026-08-03

این سند طبق الزام صریح فاز ۱ نوشته شده است: **هیچ مدل، migration، view، URL، template، CSS یا JavaScript‌ای در این کامیت تغییر نکرده است.** تنها تغییر مخزن همین فایل گزارش است.

> **راهنمای خواندن سند:** هر بخش با یکی از سه برچسب مشخص می‌شود:
> - 🔍 **FACT** — واقعیتی که مستقیماً در کد یافت شده (با ارجاع `file:line`).
> - 💡 **RECOMMENDATION** — پیشنهاد معماری من برای فاز ۲.
> - ❓ **OPEN DECISION** — تصمیمی که باید توسط کاربر/کارفرما گرفته شود، نه توسط این ممیزی.

---

## ۱. خلاصه مدیریتی (Executive Summary)

🔍 **FACT.** صفحه اصلی فروشگاه در حال حاضر یک view واحد پایتونی (`apps/catalog/views.py:home`, خط ۴۲) است که یک context dict دستی می‌سازد و آن را به یک تمپلیت ثابت (`apps/catalog/templates/catalog/home.html`) پاس می‌دهد. هیچ مفهوم عمومی «بخش/section» با قابلیت فعال/غیرفعال‌سازی، ترتیب‌دهی یا پیکربندی per-store وجود ندارد. هدر و فوتر هم به‌طور کامل درون `templates/base.html` (۳۰۲ خط) hard-code شده‌اند.

🔍 **FACT.** اپ `apps/content` از قبل بخش قابل‌توجهی از عناصر بصری مورد نیاز (اسلایدر هیرو، بنر تبلیغاتی، منوی ناوبری، لینک‌های اجتماعی، صفحات محتوایی، تنظیمات فوتر) را با یک الگوی امن مشترک برای لینک‌ها (`DestinationMixin`) پیاده‌سازی کرده است. `apps/content/README.md` صراحتاً می‌نویسد که پیاده‌سازی `HomepageLayout` **عمداً** از این اپ حذف شده تا از «تعمیم زودهنگام» جلوگیری شود — یعنی معماران قبلی همین قدم بعدی (سازنده بصری) را از قبل پیش‌بینی کرده‌اند.

🔍 **FACT — یافته بحرانی.** از میان مدل‌های `apps/content`، تنها `FooterSettings`، `FooterTrustBadge` و `FooterPaymentLogo` به یک فروشگاه (`Store`) مقیّد هستند. `HeroSlide`، `PromotionalBanner`، `SocialLink`، `Menu`، `MenuItem` و `ContentPage` هیچ فیلد `store` ندارند — یعنی در حال حاضر **سراسر پلتفرم مشترک هستند**، نه هر فروشگاه جداگانه. این یک نقص پیش‌از-موجود است که باید پیش یا همزمان با ساخت سازنده بصری رفع شود، وگرنه سازنده بصری یک ویژگی per-store روی داده‌ای global بنا خواهد شد.

💡 **RECOMMENDATION خلاصه.** به‌جای ساخت یک سیستم موازی، فاز ۲ باید: (۱) مدل‌های `apps/content` را store-scoped کند، (۲) یک مدل نسخه‌بندی‌شدهٔ چیدمان صفحه اصلی (`StorefrontLayout` + نسخه‌ها) اضافه کند که به بخش‌های ثابت/از‌پیش‌تعریف‌شده (نه HTML/JS دلخواه) ارجاع می‌دهد، (۳) یک Section Registry سمت سرور برای allowlist انواع بخش تعریف کند، (۴) الگوی موجود drag-and-drop (بدون کتابخانه خارجی، Alpine + HTML5 native DnD + htmx) را عیناً برای بازچینش بخش‌ها به کار گیرد.

---

## ۲. معماری فعلی فروشگاه (Current Storefront Architecture)

### ۲.۱ مسیریابی چندمستأجری (Multi-tenant routing)

🔍 **FACT.** درخواست‌ها بر اساس هاست از میان سه URLconf مسیریابی می‌شوند، توسط `PlatformHostRoutingMiddleware` (`apps/portal/middleware.py:17-32`):
- `shop_core.urls` — پیش‌فرض؛ هم storefront عمومی و هم پنل مدیریت مرچنت (`apps/dashboard`) از همین URLconf سرویس می‌گیرند (تفکیک بر اساس subpath، نه هاست).
- `shop_core.urls_platform` — هاست‌های مارکتینگ/پورتال مالک پلتفرم.
- `shop_core.urls_platform_admin` — هاست‌های کارکنان پلتفرم.

🔍 **FACT.** تفکیک Store انجام می‌شود در `apps/stores/resolution.py` (۵۳۳ خط):
- `resolve_store_for_storefront(request)` — مسیر عمومی storefront؛ در صورت نامعتبر بودن دامنه یا Store غیرفعال، `Http404` می‌دهد؛ در صورت Store موجود ولی «قابل‌مشاهده عمومی نبودن»، `PermissionDenied` (۴۰۳) می‌دهد.
- `resolve_store_for_admin_request(request)` — مسیر جدای پنل مدیریت.
- `domain_is_eligible_for_routing(...)` — نیازمند `Store.status=ACTIVE` + `StoreDomain.status=VERIFIED` + عدم retire شدن دامنه.
- `resolve_compatibility_store()` — یک fallback باریک برای توسعهٔ محلی تک‌فروشگاهی (نامش در کد به یک فروشگاه توسعه به‌نام «akhlaghi» اشاره دارد) — **نباید در معماری جدید به آن تکیه شود**.
- `StoreResolutionMiddleware` (`apps/stores/middleware.py:36-43`) نتیجه را روی `request.store` کش می‌کند.

🔍 **FACT.** `apps/catalog/views.py:home` مقدار `store` را از `resolve_store_for_storefront(request)` می‌گیرد (خط ۴۳) — یعنی صفحه اصلی از قبل کاملاً tenant-aware است؛ سازنده بصری باید همین الگو را ادامه دهد.

### ۲.۲ صفحه اصلی — جریان رندر فعلی

🔍 **FACT.** `home()` (`apps/catalog/views.py:42-89`) این کوئری‌ها/داده‌ها را می‌سازد (خط به خط):
- خط ۴۴: `storefront_listing_products(store)` — محصولات قابل‌نمایش فروشگاه (از `apps/catalog/services/product_publish_service.py`).
- خط ۴۶-۴۸: `top_categories` — دسته‌های ریشه فعال، مرتب بر اساس `order,name`.
- خط ۴۹-۵۳: `icon_categories` — زیردسته‌های فعال.
- خط ۵۵: `new_products` — ۸ محصول جدید (`-created_at`).
- خط ۵۶-۵۹: `discounted_products` — ۶ محصول با `discount_percent__gt=0`.
- خط ۶۰-۶۱: `highlight_product`, `most_viewed_product`.
- خط ۶۳: میانگین امتیاز و حداکثر تخفیف (aggregate).
- خط ۶۸: `_best_products(store, DEFAULT_SORT)` — پرفروش‌ترین‌ها بر اساس `sold_count` (فیلد موجود، اما بدون writer — به بخش ۸ مراجعه شود).
- خط ۸۰: `blog_posts` — ۵ پست وبلاگ آخر (بدون فیلتر store — به بخش ۸ مراجعه شود؛ `BlogPost` بیرون از این ممیزی است چون اپ جداگانه‌ای است، اما رفتار مشابه content دارد).
- خط ۸۱: `special_offer_deadline` — **هر بار از نو محاسبه می‌شود** (`timezone.now() + timedelta(hours=8)`) — یعنی شمارش‌معکوس واقعاً زمان‌بندی‌شده نیست.
- خط ۸۲-۸۷: `hero_slides`, `promo_banners` از `apps/content.models` — بدون فیلتر `store=` (چون این مدل‌ها اصلاً فیلد store ندارند).

🔍 **FACT.** `apps/catalog/templates/catalog/home.html` (۲۳۰ خط) این بخش‌ها را به ترتیب ثابت رندر می‌کند: نوار اعلان، هیرو (فقط اسلاید اول)، دسته‌های تایل/آیکون، محصولات جدید، پرفروش‌ترین (با تب مرتب‌سازی)، تخفیف‌دار، بنر شمارش‌معکوس تخفیف، بنرهای تبلیغاتی، ردیف اعتماد (hard-coded)، وبلاگ، خبرنامه (غیرفعال). ترتیب و حضور/غیاب این بخش‌ها **در تمپلیت hard-code شده و به‌هیچ‌وجه per-store قابل تغییر نیست**.

### ۲.۳ هدر

🔍 **FACT.** هدر یک partial مستقل نیست — کاملاً درون `templates/base.html` (بلوک `{% block header %}` خط ۲۸ تا حدود خط ۱۳۵) جاسازی شده: نوار اعلان، نوار هدر (لوگو/جستجو/حساب کاربری/سبد خرید/علاقه‌مندی‌ها)، نوار ناوبری (منوی دسته‌بندی کشویی + منوی موقعیت `header` از مدل `Menu`). هیچ مکانیزم پیکربندی ترتیب/نمایش عناصر هدر per-store وجود ندارد؛ تنها بخش پویا، منوی `Menu(location="header")` است.

### ۲.۴ فوتر

🔍 **FACT.** فوتر هم درون `base.html` (بلوک `{% block footer %}` خط ۱۴۱ تا حدود خط ۲۵۲) جاسازی شده، اما به‌مراتب پیکربندی‌پذیرتر از هدر است: `FooterSettings` (مدل store-scoped، `apps/content/models.py:601-684`) حدود ۲۰ فیلد boolean/char برای toggle کردن بخش‌های مختلف فوتر (توضیحات، تماس، لینک‌های مفید، دسته‌ها، شبکه‌های اجتماعی، اعتماد/اینماد، کپی‌رایت، خبرنامه) دارد. `FooterTrustBadge`/`FooterPaymentLogo` هم store-scoped هستند (FK مستقیم، نه از طریق FooterSettings). موقعیت منوی `footer_3` در مدل `Menu` تعریف شده اما در تمپلیت **استفاده نمی‌شود** (کد مرده).

### ۲.۵ تم/برندینگ

🔍 **FACT.** `ShopSettings` (`apps/core/models.py:38`) یک ردیف به‌ازای هر Store (`OneToOneField`) با هفت فیلد رنگ hex (`primary_color`, `accent_color`, `secondary_color`, `background_color`, `surface_color`, `text_color`, `muted_text_color` — خطوط ۱۳۶-۱۴۸)، `logo`/`favicon` (ImageField). **هیچ فیلد فونتی در کل پایگاه‌کد وجود ندارد** — یک نقص تأیید‌شده.

🔍 **FACT.** `apps/core/theme_presets.py` شش پیش‌تنظیم رنگی داخلی (`THEME_PRESETS`) دارد. `VisualIdentityForm` (در `apps/dashboard/forms.py`) نسبت کنتراست WCAG را از طریق `apps/core/color_utils.py` (`contrast_ratio`, `foreground_for`, `mix_hex`, `darken_hex`) اعتبارسنجی می‌کند.

🔍 **FACT.** رنگ‌ها از طریق CSS custom properties که مستقیماً روی attribute `style=` تگ `<html>` تزریق می‌شوند اعمال می‌گردند (`apps/core/context_processors.py:shop_settings`)، و توسط `apps/core/static/css/tokens.css` با `var(--brand-*, fallback)` مصرف می‌شوند — یعنی **نه یک stylesheet تولیدی، نه بلوک `<style>` inline**، بلکه یک attribute مستقیم روی ریشهٔ سند.

### ۲.۶ سئو

🔍 **FACT.** هیچ سرویس سئوی متمرکز وجود ندارد. هر نوع صفحه بلوک‌های `title`/`meta_description`/`robots_meta`/`canonical`/`og_tags`/`structured_data` تعریف‌شده در `base.html` را override می‌کند. `apps/core/seo.py` (۸۲ خط) صرفاً مولّد `sitemap.xml`/`robots.txt` است، نه سرویس متادیتا.

### ۲.۷ کش

🔍 **FACT.** هیچ لایه کشی روی رندر storefront وجود ندارد (بدون `CACHES` سفارشی فراتر از `LocMemCache` پیش‌فرض ضمنی جنگو، بدون `cache_page`، بدون fragment caching) — تأیید‌شده با grep جامع.

### ۲.۸ Middleware و Context Processors (فهرست کامل)

🔍 **FACT.** ترتیب دقیق میان‌افزارها و context processorهای ثبت‌شده (۹ میان‌افزار، ۱۷ context processor) در `shop_core/settings.py` یافت شد؛ مرتبط‌ترین‌ها برای این ممیزی: `PlatformHostRoutingMiddleware` (تعیین URLconf)، `StoreResolutionMiddleware` (تعیین `request.store`)، و context processor `shop_settings` (تزریق تم).

---

## ۳. سامانه‌های سفارشی‌سازی موجود (Existing Customization Capabilities)

🔍 **FACT — جدول خلاصه (نتیجه ممیزی مستقیم و دو Explore agent مستقل):**

| بخش صفحه اصلی | وضعیت | جزئیات |
|---|---|---|
| نوار اعلان | ⚠️ PARTIAL | نوار hard-code؛ فقط یک آستانه عددی از DB می‌آید |
| بنر هیرو | ⚠️ PARTIAL | مدل `HeroSlide` چند اسلاید پشتیبانی می‌کند، اما فقط `slide[0]` رندر می‌شود — بدون کاروسل/اسلایدر JS |
| بنر/اسلایدر چندتایی | ❌ ABSENT | `PromotionalBanner`ها به‌صورت ستونی/عمودی چیده می‌شوند؛ بدون JS اسلایدر |
| گرید دسته‌بندی | ⚠️ PARTIAL | موقعیتی (۳ یا ۴ دستهٔ اول)؛ بدون فلگ `is_featured` |
| محصولات ویژه (featured) | ❌ ABSENT | هیچ فیلد `is_featured` در `Product` نیست |
| جدیدترین محصولات | ✅ EXISTS | `order_by("-created_at")[:8]` |
| پرفروش‌ترین | ⚠️ PARTIAL | فیلد `Product.sold_count` هست (`apps/catalog/models.py:177`) اما **هیچ کدی آن را از سفارش‌ها افزایش نمی‌دهد** |
| تخفیف‌دار | ✅ EXISTS | `discount_percent`, `compare_at_price` |
| پیشنهاد شگفت‌انگیز/فلش‌سیل | ⚠️ PARTIAL | ددلاین هر بار در هر page-load از نو محاسبه می‌شود؛ ذخیره/پیکربندی‌پذیر نیست |
| کاروسل برند | ❌ ABSENT | مدل `Brand` فقط به‌عنوان فیلتر لیست محصول استفاده می‌شود |
| کارت‌های تبلیغاتی چندستونه | ❌ ABSENT | مفهوم مجزایی وجود ندارد |
| بخش متن+تصویر/rich-text | ❌ ABSENT | `ContentPage.body` متن ساده است (`linebreaksbr`)، بدون فیلد تصویر، CKEditor به آن وصل نیست |
| ویدیو در صفحه اصلی | ❌ ABSENT | فقط `ProductVideo` سطح محصول |
| ردیف اعتماد/ویژگی‌ها (صفحه اصلی) | ⚠️ PARTIAL | ردیف صفحه اصلی کاملاً hard-code؛ نشان‌های اعتماد فوتر (`FooterTrustBadge`) جداگانه و admin-configurable هستند |
| نظرات مشتریان (Testimonials) | ❌ ABSENT | فقط سیستم Review سطح محصول |
| کارت‌های وبلاگ/محتوا | ⚠️ PARTIAL | مدل `BlogPost` هست، ۵ پست آخر رندر می‌شود، اما بدون رابط CRUD در داشبورد (فقط Django admin) و لینک‌های «همه مطالب»/«ادامه مطلب» مرده (`href="#"`) |
| خبرنامه | ⚠️ PARTIAL | ورودی/دکمه `disabled`، بدون endpoint بک‌اند، بدون مدل مشترک |
| صفحات سفارشی | ✅ EXISTS | `ContentPage` — کاملاً از داشبورد مدیریت‌پذیر |
| فاصله‌گذار/جداکننده (spacer) | ❌ ABSENT | هیچ primitive قابل‌استفاده مجدد |

🔍 **FACT — نتیجه‌گیری معماری (تأیید‌شده مستقل توسط من و agent).** هر بخش صفحه اصلی فعلاً یک context dict دستی پایتونی درون یک تمپلیت ثابت است؛ هیچ لیست مرتب «sections»، هیچ مکانیزم فعال/غیرفعال/ترتیب‌دهی per-store، و هیچ abstraction عمومی «block» وجود ندارد.

---

## ۴. فایل‌ها و اپ‌های مرتبط (تمام مخزن جست‌وجو شد)

🔍 **FACT — فهرست فایل‌های کلیدی یافت‌شده در سراسر مخزن (نه فقط یک اپ):**

| مسیر | نقش |
|---|---|
| `apps/catalog/views.py` | `home()` — منطق اصلی رندر صفحه اصلی |
| `apps/catalog/templates/catalog/home.html` | تمپلیت صفحه اصلی |
| `apps/catalog/services/product_publish_service.py` | منبع الگوی «قابل‌مشاهده بودن» زمان‌بندی‌شده (`storefront_visible_products`) |
| `apps/content/models.py` | `DestinationMixin`, `HeroSlide`, `PromotionalBanner`, `SocialLink`, `Menu`, `MenuItem`, `ContentPage`, `FooterSettings`, `FooterTrustBadge`, `FooterPaymentLogo` |
| `apps/content/README.md` | مستندسازی صریح تصمیم به تعویق‌انداختن `HomepageLayout` |
| `apps/content/services.py` | `resolve_destination_url` و کمکی‌های مرتبط با `DestinationMixin` |
| `apps/content/views.py`, `apps/content/urls.py` | فقط `page_detail` (نمایش عمومی `ContentPage`) — بسیار کوچک |
| `apps/dashboard/views.py` (خطوط ~۴۱۴۹–۴۳۸۰) | CRUD مدیریتی هیرو/بنر (بدون store-scoping، بدون reorder) |
| `apps/dashboard/urls.py` (خطوط ۱۹۵–۲۰۴) | مسیرهای `homepage/hero/*` و `homepage/banners/*` |
| `apps/dashboard/decorators.py` | `staff_required` + `permission_required` — الگوی مرجع تفکیک مستأجر |
| `apps/stores/authorization.py` | ثابت‌های مجوز (`CONTENT_MANAGE`, `MEDIA_MANAGE`, ...) |
| `apps/stores/resolution.py`, `apps/stores/middleware.py` | تفکیک Store بر اساس هاست |
| `apps/portal/middleware.py` | سوییچ سه‌گانه URLconf |
| `apps/core/models.py` | `ShopSettings` (تم/برندینگ) |
| `apps/core/theme_presets.py`, `apps/core/color_utils.py` | پیش‌تنظیم‌های رنگی، اعتبارسنجی کنتراست |
| `apps/core/context_processors.py` | تزریق متغیرهای تم به همه تمپلیت‌ها |
| `apps/core/seo.py` | sitemap/robots (نه متادیتای سئو) |
| `apps/core/storage.py` | `PrivateFileSystemStorage` (ADR-52) |
| `apps/catalog/services/html_sanitizer.py` | ساینیتایزر HTML مبتنی بر BeautifulSoup (allowlist tag/attr/style/scheme) |
| `apps/catalog/services/product_image_service.py` | اعتبارسنجی/پردازش تصویر مخصوص گالری محصول |
| `apps/portal/services/handoff_service.py` | تنها الگوی signed-token (`TimestampSigner`) موجود در کل مخزن |
| `apps/blog/models.py` | `BlogPost` — مرتبط با بخش «مطالب» صفحه اصلی |
| `templates/base.html` | تمپلیت پایه — هدر/فوتر hard-code |
| `apps/core/static/css/tokens.css` | مصرف‌کننده CSS variableهای تم |
| `apps/core/static/js/vendor/ckeditor5-classic/` | باندل CKEditor5 self-hosted |

💡 **RECOMMENDATION.** به‌دلیل پراکندگی فایل‌های مرتبط بین `apps/catalog`، `apps/content`، `apps/dashboard`، `apps/core` و `apps/portal`، سازنده بصری باید یک اپ جدید و مستقل (`apps/storefront_builder` یا مشابه) داشته باشد که این اپ‌های موجود را **مصرف** می‌کند (import می‌کند)، نه اینکه منطق را در یکی از آن‌ها تکرار کند.

---

## ۵. جریان رندر صفحه اصلی (تکرار تخصصی)

🔍 **FACT.** ترتیب اجرا: `PlatformHostRoutingMiddleware` → `StoreResolutionMiddleware` (`request.store` تنظیم می‌شود) → `home(request)` → `resolve_store_for_storefront(request)` (دوباره، مستقل از middleware — تکرار عمدی برای سخت‌گیری تفکیک مستأجر) → ساخت context dict مسطح → رندر `catalog/home.html` که `{% extends "base.html" %}` است.

---

## ۶. جریان رندر هدر/فوتر

🔍 **FACT.** هدر/فوتر بخشی از `base.html` هستند و در **هر** رندر صفحه (نه فقط صفحه اصلی) اجرا می‌شوند، چون همه تمپلیت‌های storefront از `base.html` ارث می‌برند. این یعنی هر تغییری در طراحی هدر/فوتر برای سازنده بصری، از طریق `context_processors` باید در دسترس تمام صفحات (نه فقط صفحه اصلی) باشد.

---

## ۷. معماری تم فعلی (تکرار)

🔍 **FACT.** به بخش ۲.۵ مراجعه شود. نکته کلیدی برای فاز ۲: مکانیزم تزریق فعلی (inline `style=` روی `<html>`) با یک مدل چیدمان صفحه‌ای که رنگ/فونت را per-section override می‌کند سازگار است، چون واحد تزریق «صفحه» است نه «بخش» — برای override رنگ در سطح بخش باید یک لایه CSS variable محلی (مثلاً `style` روی wrapper هر بخش) اضافه شود.

---

## ۸. شکاف‌های فعلی (Current Gaps)

🔍 **FACT — فهرست کامل شکاف‌های تأیید‌شده:**

1. **بدون store-scoping**: `HeroSlide`, `PromotionalBanner`, `SocialLink`, `Menu`, `MenuItem`, `ContentPage` بین همه فروشگاه‌ها مشترک‌اند.
2. **بدون reorder endpoint**: هیچ‌کدام از `HeroSlide`/`PromotionalBanner`/`MenuItem`/`SocialLink`/`FooterTrustBadge`/`FooterPaymentLogo` دارای endpoint بازچینش (drag-and-drop) نیستند؛ فقط افزودن/ویرایش/حذف/toggle.
3. **کاروسل هیرو کار نمی‌کند**: مدل چند اسلاید پشتیبانی می‌کند، ولی فقط اسلاید اول رندر می‌شود.
4. **`sold_count` بدون writer**: فیلد برای «پرفروش‌ترین» استفاده می‌شود اما هیچ کد سفارشی آن را افزایش نمی‌دهد.
5. **شمارش‌معکوس غیرواقعی**: `special_offer_deadline` هر page-load از نو محاسبه می‌شود.
6. **بدون فیلد فونت** در `ShopSettings`.
7. **بدون کش** روی رندر storefront.
8. **بدون مدل چیدمان عمومی**: هیچ لیست section مرتب‌شونده وجود ندارد.
9. **بدون rich-text در سطح صفحه اصلی**: CKEditor فقط به توضیحات محصول وصل است.
10. **خبرنامه غیرفعال است** (بدون بک‌اند).
11. **بدون CRUD داشبورد برای BlogPost** (فقط Django admin).
12. **بدون مدل Testimonial/نظر مستقل از محصول.**
13. **بدون preview token امن**؛ پیش‌نمایش فعلی صرفاً session-auth + تفکیک store است (مشابه الگوی `product_preview`).
14. **بدون versioning/rollback عمومی** — تنها نمونهٔ نسخه‌بندی rollback-capable در کل مخزن، جفت `IndustryTemplate`/`StoreTemplateUpdate` است.
15. **دو پیاده‌سازی مستقل و کمی متفاوت اعتبارسنجی تصویر** (`apps/content/models.py` در برابر `apps/catalog/services/product_image_service.py`) — بدون مدل رسانه مشترک.

---

## ۹. نگاشت الزامات تأییدشده (Requirements Mapping)

🔍 **FACT/💡 RECOMMENDATION ترکیبی — نگاشت الزامات فاز ۲ به وضعیت فعلی:**

| الزام تأییدشده | وضعیت فعلی | اقدام لازم در فاز ۲ |
|---|---|---|
| هدر: لوگو/نام/جستجو/منو/دسته/ورود/سبد | همه در `base.html` موجودند اما ثابت | مدل پیکربندی هدر (نمایش/ترتیب) + استفاده از `Menu(location="header")` موجود |
| هدر: نوار اعلان، sticky | نوار اعلان hard-code | فیلد فعال/متن/رنگ در مدل جدید |
| فوتر | بسیار پیکربندی‌پذیر از قبل (`FooterSettings`) | گسترش، نه بازنویسی |
| هیرو/بنر/اسلایدر | مدل هست، رندر ناقص | فعال‌سازی چرخهٔ کامل اسلاید‌ها + تبدیل به یک نوع section |
| گرید دسته، محصولات ویژه/جدید/پرفروش/تخفیف‌دار | اکثراً service-level موجودند | تبدیل به data source های Section Registry |
| برند، کارت تبلیغاتی، متن+تصویر، اعتماد، خبرنامه | عمدتاً غایب | نوع section جدید، با استفاده از primitive های موجود (`DestinationMixin`, sanitizer) |
| ادیتور بصری کامل (drag/duplicate/...) | بدون معادل مستقیم | بخش‌های ۹ و ۱۶ این گزارش |
| Draft/Preview/Publish | سه الگوی مستقل و ناسازگار موجود | بخش ۱۴ این گزارش — طراحی واحد پیشنهادی |

---

## ۱۰. مدل داده پیشنهادی (Recommended Data Model)

💡 **RECOMMENDATION.** گزینه **C (هیبرید)** پیشنهاد می‌شود: یک سند JSON نسخه‌بندی‌شده برای *چیدمان* (ترتیب و روشن/خاموش بودن بخش‌ها و تنظیمات سطحِ‌بخش) + مدل‌های نرمال‌شده برای *مالکیت و ارجاع* (کدام section type، متعلق به کدام Store، کدام نسخه). دلیل رد سایر گزینه‌ها:

- **گزینه A (سند JSON خالص)** رد می‌شود چون: بدون schema سطح دیتابیس امکان اعتبارسنجی force نمی‌شود؛ کوئری/فیلتر بر اساس نوع section یا وضعیت انتشار دشوار می‌شود؛ audit-log دقیق (کدام بخش عوض شد) سخت است.
- **گزینه B (کاملاً نرمال‌شده: `StorefrontLayout`/`StorefrontLayoutVersion`/`StorefrontSection`/`StorefrontSectionSetting`)** رد می‌شود چون: هر تغییر تنظیمات یک بخش نیازمند چند ردیف `StorefrontSectionSetting` جداگانه است (N+1 بالقوه)، بازچینش نیازمند بازنویسی چند ردیف `order` هم‌زمان است، و schema per-section-type به‌سختی در ستون‌های عمومی جا می‌شود.
- **گزینه C (هیبرید)** انتخاب می‌شود چون:
  - **توسعه‌پذیری**: افزودن نوع section جدید فقط نیازمند افزودن ورودی در Section Registry است، نه migration.
  - **اعتبارسنجی**: هر ردیف `StorefrontSection` دارای `section_key` (allowlist از Registry) و `settings` (JSONField) است که با schema هر نوع (بخش ۱۲) اعتبارسنجی می‌شود — نه در `clean()` بلکه در سرویس (مطابق قرارداد موجود پروژه که همه‌ی JSONField ها را همان‌طور اعتبارسنجی می‌کند).
  - **تفکیک مستأجر**: `StorefrontLayout` دارای `store = OneToOneField(Store)` است (مطابق الگوی `FooterSettings`/`ShopSettings`).
  - **نسخه‌بندی/rollback**: `StorefrontLayoutVersion` هر نسخه را immutable نگه می‌دارد (مشابه دقیق الگوی `IndustryTemplate` با `content_fingerprint`) — بازگردانی یعنی صرفاً تغییر اشاره‌گر published_version.
  - **کارایی**: `StorefrontSection` ردیف‌های نرمال‌شده با `order` هستند — بازچینش با همان الگوی موجود `bulk_update` انجام می‌شود؛ محتوای تنظیمات هر بخش در همان ردیف (JSONField) است، نه در جدول جدا — یک کوئری `select_related`/`prefetch_related` برای کل چیدمان کافی است.
  - **پیش‌نمایش/انتشار**: نسخه Draft و نسخه Published دو ردیف `StorefrontLayoutVersion` جدا هستند؛ انتشار یعنی یک تراکنش اتمیک که `published_version_id` را عوض می‌کند (نه کپی کردن محتوا).
  - **قالب‌های صنعتی/آینده**: نسخه اولیه یک store می‌تواند از یک `StorefrontLayoutVersion` قالب صنعتی «کلون» شود (الگوی مشابه seed کردن IndustryTemplate).

### طرح جداول پیشنهادی (سطح مفهومی — بدون migration در این فاز)

- `StorefrontLayout` (۱ به ۱ با Store؛ اشاره‌گر به `published_version`، `draft_version`)
- `StorefrontLayoutVersion` (append-only؛ `status` = draft/published/archived؛ `created_by`، `content_fingerprint`)
- `StorefrontSection` (FK به `StorefrontLayoutVersion`؛ `section_key`؛ `order`؛ `is_active`؛ `settings` JSONField؛ `publish_at` اختیاری — با الگوی `Product.publish_at`)
- `StorefrontHeaderConfig` / `StorefrontFooterConfig` (۱ به ۱ با Store یا با هر `StorefrontLayoutVersion` — به بخش ۱۳ مراجعه شود؛ تصمیم باز)

❓ **OPEN DECISION.** آیا هدر/فوتر باید در همان `StorefrontLayoutVersion` (یعنی نسخه‌بندی و draft/publish مشترک با صفحه اصلی) قرار گیرند، یا یک پیکربندی جدا و مستقیماً published (بدون draft) باشند؟ به بخش ۱۳ مراجعه شود.

---

## ۱۱. گزینه‌های جایگزین بررسی‌شده

💡 **RECOMMENDATION (تحلیل رد گزینه‌ها).** به بخش ۱۰ مراجعه شود — گزینه‌های A و B به همراه دلایل دقیق رد آن‌ها آنجا مستند شده تا از تکرار خودداری شود.

---

## ۱۲. طراحی Section Registry

💡 **RECOMMENDATION.** یک دیکشنری پایتونی سمت سرور (نه دیتابیس) با ساختار زیر برای هر کلید section:

```python
SectionDefinition(
    key="hero_banner",                 # شناسه پایدار، در settings.section_key ذخیره می‌شود
    label_fa="بنر هیرو",
    icon="image",
    settings_schema=HeroBannerSettingsSchema,   # اعتبارسنجی JSON، نه clean() مدل
    allowed_data_source="hero_slides",          # کدام سرویس/کوئری داده می‌دهد
    template_name="storefront/sections/hero_banner.html",
    default_config={...},
    min_instances=0, max_instances=1,
    duplicable=False,
    removable=True,
)
```

نمونه کلیدها طبق الزامات: `hero_banner`, `image_slider`, `category_grid`, `featured_products`, `newest_products`, `best_sellers`, `discounted_products`, `amazing_offers`, `brand_carousel`, `promo_cards`, `rich_text`, `image_text`, `trust_features`, `newsletter`.

**پیشگیری از حملات (نکات کلیدی):**
- بارگذاری template همیشه از یک نگاشت **ثابت پایتونی** (`template_name` هارد‌کد در Registry)، هرگز از رشته‌ای که کاربر کنترل می‌کند — این از template injection/arbitrary file load جلوگیری می‌کند.
- `section_key` هر ردیف `StorefrontSection` باید عضو کلیدهای Registry باشد (allowlist سختگیرانه در سرویس ذخیره‌سازی)؛ کلید ناشناخته رد می‌شود.
- هیچ import پویا/`importlib`/`eval` بر اساس داده کاربر مجاز نیست — Registry یک ماژول پایتونی است که در deploy-time ثابت می‌شود.
- `settings` هر section با `settings_schema` مربوط به همان `key` اعتبارسنجی می‌شود (مثلاً با `django.forms` یا pydantic سبک، مطابق با قرارداد فعلی پروژه که schema همیشه در سرویس چک می‌شود نه در مدل).
- هر رفرنس به Product/Category/Brand/Banner درون `settings` باید در سرویس اعتبارسنجی شود که آن آبجکت متعلق به همان Store است (با همان الگوی `_get_scoped_product`).
- HTML آزاد در `settings` (مثلاً برای `rich_text`) از طریق ساینیتایزر موجود (`apps/catalog/services/html_sanitizer.py`) عبور داده می‌شود — همان allowlist tag/attr/style/scheme.

---

## ۱۳. طراحی هدر/فوتر

💡 **RECOMMENDATION.** هدر/فوتر باید به‌عنوان **پیکربندی جدا و مستقیم روی Store** (نه بخشی از `StorefrontLayoutVersion` قابل draft) مدل شوند، اما با یک لایه Draft/Publish سبک مخصوص به خودشان — دلیل: هدر/فوتر در *هر* صفحه رندر می‌شوند (نه فقط صفحه اصلی)، پس تغییرشان ریسک بیشتری برای کل storefront دارد و باید چرخه انتشار مستقل و آشکارتری داشته باشد، اما همچنان نیاز به پیش‌نمایش قبل از انتشار دارند.

**عناصر اجباری/غیرقابل‌حذف (برای جلوگیری از شکستن ناوبری):**
- دسترسی به سبد خرید (cart icon/link) — همیشه باید رندر شود.
- حداقل یک راه ورود به صفحه اصلی (لوگو یا لینک خانه).
- منوی موبایل نباید بدون آیتم قابل‌کلیک بماند.
- فوتر باید حداقل یک ستون فعال داشته باشد (نمی‌توان همه ستون‌ها را غیرفعال کرد).

سرویس ذخیره‌سازی باید این محدودیت‌ها را validation-time اجرا کند (نه فقط UI-level)، دقیقاً مطابق سبک موجود پروژه (اعتبارسنجی سرویس، نه صرفاً فرم).

---

## ۱۴. طراحی Draft/Preview/Publish

💡 **RECOMMENDATION.** بر پایه الگوی گزینه C (بخش ۱۰):
- **حالت‌ها**: `published` (فعلاً زنده)، `draft` (در حال ویرایش، حداکثر یک draft فعال به‌ازای هر Store)، و آرشیو نسخه‌های قبلی (`archived`، فقط‌خواندنی، برای rollback).
- **ذخیره draft**: نوشتن روی `StorefrontLayoutVersion(status=draft)` موجود؛ بدون اثر روی storefront عمومی.
- **پیش‌نمایش**: باید فقط برای کاربر staff با `permission_required(CONTENT_MANAGE)` در دسترس باشد؛ چون پیش‌نمایش صرفاً برای merchant خودِ فروشگاه است (نه لینک قابل‌اشتراک با بیرون)، **الگوی ساده‌تر و کافی `product_preview` توصیه می‌شود** (session-auth + تفکیک store)، نه ساخت مکانیزم توکن امضاشدهٔ جدید — مگر اینکه نیاز به لینک پیش‌نمایش قابل‌اشتراک با افراد خارج از پنل (مثلاً برای تأیید مشتری) وجود داشته باشد.
- **انتشار (publish)**: عملیات اتمیک درون `transaction.atomic()` که تنها یک فیلد اشاره‌گر (`StorefrontLayout.published_version_id`) را عوض می‌کند؛ محتوای نسخه از قبل کامل و معتبر است (چون در زمان ذخیره‌ی draft همیشه اعتبارسنجی شده) — این یعنی انتشار ناموفق هرگز نمی‌تواند نیمه‌کاره storefront زنده را جایگزین کند، چون تغییر فقط یک FK است.
- **discard**: حذف/بایگانی نسخه draft بدون اثر روی published.
- **restore**: کپی محتوای یک نسخه آرشیوشده به یک draft جدید (نه بازگرداندن مستقیم published، تا امکان پیش‌نمایش قبل از تأیید باقی بماند).

❓ **OPEN DECISION.** آیا restore باید مستقیماً منتشر شود یا ابتدا یک draft بسازد برای تأیید نهایی؟ پیشنهاد من گزینه دوم (ایمن‌تر) است، اما تصمیم نهایی با کاربر است.

---

## ۱۵. نسخه‌بندی و Rollback

🔍 **FACT (الگوی مرجع).** `IndustryTemplate`/`StoreTemplateUpdate` تنها نمونه rollback-capable موجود در مخزن است: ردیف‌های immutable-per-version (`UniqueConstraint(slug, version)`)، `content_fingerprint` (SHA-256) برای تشخیص drift، و یک مدل ممیزی append-only جدا.

💡 **RECOMMENDATION.** همین الگو برای `StorefrontLayoutVersion` تکرار شود: هر نسخه پس از publish هرگز mutate نمی‌شود (ویرایش بعدی یعنی ساخت نسخه draft جدید از روی کپی)؛ `content_fingerprint` برای تشخیص تغییرات غیرمنتظره؛ تاریخچه کامل نسخه‌ها همیشه قابل مشاهده و restore.

---

## ۱۶. معماری Drag-and-Drop

🔍 **FACT (الگوی موجود، عیناً قابل استفاده مجدد).** الگوی دقیق در `apps/dashboard/templates/dashboard/partials/product_images_list.html` و `brands_table.html`: کانتینر `x-data="{dragId:null}"`، هر آیتم `draggable="true" data-id="{{pk}}"`، `@dragstart`/`@dragover.prevent`/`@drop.prevent` (با `Node.compareDocumentPosition` برای تشخیص قبل/بعد)، خواندن ترتیب نهایی از DOM، و `htmx.ajax('POST', url, {values:{x_ids: ids}, target:'#container', swap:'outerHTML'})`. بدون کتابخانه خارجی (بدون SortableJS).

🔍 **FACT (قرارداد endpoint، تکرارشده در ۵ endpoint موجود).** POST فرم‌رمزی‌شده با فیلد `<x>_ids` (لیست) → سرویس دوباره بر اساس تفکیک مستأجر فیلتر می‌کند → شناسه‌های نامعتبر/خارجی را بی‌صدا حذف می‌کند → `enumerate()` ترتیب را ۰..N بازتنظیم می‌کند → `bulk_update()` → پاسخ یک partial HTML (htmx swap) است، نه JSON.

💡 **RECOMMENDATION.** همین قرارداد برای بازچینش section ها استفاده شود: `section_ids` فرم‌رمزی‌شده → سرویس فیلتر بر اساس `StorefrontLayoutVersion` فعلیِ کاربر → drop نامعتبرها → `bulk_update(order=...)` درون `transaction.atomic()`. برای **موبایل/کیبورد** (طبق الزام صریح — «بازچینش فقط با موس کافی نیست»)، دکمه‌های fallback «بالا/پایین» باید هر ردیف section را همراهی کنند که همان endpoint را با یک آیتم جابه‌جا‌شده صدا می‌زنند — این یک الگوی جدید است (در کد فعلی برای drag موجود نیست) و باید در فاز ۲ اضافه شود.

**اعتبارسنجی سمت سرور اجباری:** بک‌اند هرگز نباید به ترتیب ارسالی از فرانت اعتماد کامل کند؛ باید دوباره فیلتر بر مالکیت/Store انجام شود، تکراری/گمشده‌ها حذف/گزارش شوند، و کل عملیات در یک تراکنش انجام شود (مطابق الگوی موجود).

---

## ۱۷. Schema پیکربندی بخش‌ها (نمونه)

💡 **RECOMMENDATION — نمونه schema برای دو نوع section (نه کد نهایی، صرفاً طرح مفهومی):**

- `hero_banner`: `{slides: [{destination_type, destination_id, image, mobile_image, title, subtitle, button_label, show_button}], autoplay: bool, interval_ms: int}`
- `featured_products`: `{data_source: "manual"|"auto_newest"|"auto_bestselling"|"auto_discounted"|"category", category_id?, product_ids?: [...], limit: int, sort: str}`

هر schema باید در سرویس (نه در `clean()` مدل) با تابعی مانند `validate_section_settings(section_key, settings, store)` بررسی شود که هم شکل داده و هم مالکیت ارجاعات (Product/Category/Brand/Banner) را به `store` چک می‌کند.

---

## ۱۸. منابع داده بخش‌ها (محصول/دسته/بنر)

🔍 **FACT.** سرویس‌های موجود از قبل منطق «قابل‌مشاهده بودن» را دارند: `storefront_visible_products`/`storefront_listing_products` (`apps/catalog/services/product_publish_service.py`). این‌ها باید مستقیماً به‌عنوان data source های `featured_products`/`newest_products`/`best_sellers`/`discounted_products` استفاده شوند، **نه بازنویسی**.

💡 **RECOMMENDATION.** هر data source باید: مالکیت Store را همیشه اعمال کند (فیلتر `store=`)، محصولات/دسته‌های غیرفعال یا حذف‌شده را حذف کند، برای لیست خالی یک empty-state آبرومند رندر کند (مطابق قرارداد مستندشده در `apps/content/README.md`: «بدون fallback سخت‌کد‌شده — بخش کامل حذف می‌شود اگر آیتم فعالی نباشد»)، و همیشه با `select_related`/`prefetch_related` و `[:N]` صریح از N+1 و کوئری نامحدود پرهیز کند.

---

## ۱۹. مجوز و تفکیک مستأجر

🔍 **FACT (الگوی مرجع، قابل کپی مستقیم).** پشته دکوراتور `@staff_required` + `@permission_required(PERMISSION_CONST)` از `apps/dashboard/decorators.py` + `apps/stores/authorization.py`. الگوی `_get_scoped_<X>(request, pk)` که همیشه `get_object_or_404(Model, pk=pk, store=_resolve_dashboard_store(request))` است. تفکیک مستأجر دوباره در لایه سرویس هم اعمال می‌شود (double-scoping در view و سرویس).

💡 **RECOMMENDATION.** یک مجوز جدید مانند `STOREFRONT_LAYOUT_MANAGE` به `apps/stores/authorization.py` اضافه شود (یا از `CONTENT_MANAGE` موجود استفاده مجدد شود اگر دامنه مفهومی هم‌پوشان کافی باشد — ❓ **OPEN DECISION**: تصمیم نهایی با کاربر). همه view/سرویس‌های جدید باید این پشته دوگانه (decorator + service-level scoping) را دقیقاً تکرار کنند.

---

## ۲۰. ریسک‌های امنیتی و کاهش آن‌ها

💡 **RECOMMENDATION (تحلیل ریسک):**

| ریسک | کاهش پیشنهادی |
|---|---|
| اجرای JavaScript دلخواه | **ممنوع در نسخه اول** — هیچ فیلد `custom_js` در هیچ section schema نباشد |
| HTML/CSS آزاد | **ممنوع در نسخه اول** برای اکثر section ها؛ فقط `rich_text` با ساینیتایزر allowlist موجود (`html_sanitizer.py`) مجاز است |
| تزریق اسکریپت از طریق URL مقصد | استفاده مجدد از `DestinationMixin` که schemeهای `javascript:`/`data:` را رد می‌کند |
| بارگذاری template دلخواه | Registry ثابت پایتونی — بدون رشته کاربر در مسیر template (بخش ۱۲) |
| ارجاع cross-store به محصول/دسته/بنر | اعتبارسنجی مالکیت در سرویس برای هر ID درون `settings` |
| CSRF روی endpointهای reorder/publish/toggle | استفاده از میان‌افزار CSRF استاندارد جنگو (از قبل فعال در تمام فرم‌های htmx موجود) |
| دسترسی غیرمجاز به پیش‌نمایش/ویرایش | پشته `staff_required`+`permission_required`+تفکیک store (بخش ۱۹) |
| نشت draft یک فروشگاه به فروشگاه دیگر | فیلتر `store=` اجباری در هر کوئری نسخه/section؛ تست‌های cross-store rejection |
| Rate limiting روی reorder/publish | فعلاً هیچ ریت‌لیمیتی در پروژه برای عملیات مشابه (drag سایر مدل‌ها) وجود ندارد — ❓ **OPEN DECISION**: آیا این محدوده باید معرفی شود یا سازگار با استاندارد فعلی پروژه (بدون rate limit) باقی بماند |

---

## ۲۱. کارایی و کش

💡 **RECOMMENDATION.**
- بارگذاری نسخه منتشرشده باید یک کوئری با `prefetch_related("sections")` باشد، نه N کوئری جدا به‌ازای هر section.
- کش published layout (نه draft) با کلید `store_id` + `published_version_id`؛ invalidate در همان تراکنش atomic که publish انجام می‌شود.
- پیش‌نمایش draft همیشه باید کش را **دور بزند** (bypass) چون محتوای در حال تغییر است.
- کش نتایج data source محصول (مثلاً «پرفروش‌ترین») باید هنگام تغییر سفارش/موجودی invalidate شود — نیازمند هماهنگی با سیگنال‌های اپ `orders` (خارج از محدوده این ممیزی، صرفاً یادداشت وابستگی).
- تصاویر باید lazy-load شوند (`loading="lazy"`) و نسخه موبایل جدا داشته باشند (الگوی موجود `desktop_image`/`mobile_image` در `HeroSlide`/`PromotionalBanner` باید برای همه section های تصویری تکرار شود).

---

## ۲۲. طراحی موبایل/واکنش‌گرا

💡 **RECOMMENDATION.** طبق الزام صریح («یک ادیتور فقط-دسکتاپ قابل‌قبول نیست»)، ادیتور باید در ۴ عرض تست شود: 1440 (دسکتاپ کامل، پنل تنظیمات کنار پیش‌نمایش)، 1024 (تبلت — پنل تنظیمات ممکن است به‌صورت modal/drawer شود)، 768 (تبلت عمودی — لیست section و پیش‌نمایش می‌تواند تب‌بندی شود)، 390 (موبایل — drag با دکمه‌های fallback بالا/پایین باید حتماً کار کند، چون drag لمسی نامطمئن‌تر است؛ کنترل‌های دستگاه پیش‌نمایش desktop/tablet/mobile باید در تمام عرض‌ها در دسترس بمانند بدون اسکرول افقی کل صفحه).

---

## ۲۳. سازگاری با نسخه قبل و مهاجرت

💡 **RECOMMENDATION (طبق الزام صریح «هیچ فروشگاهی نباید صفحه اصلی خالی دریافت کند»).**
- برای هر Store موجود، یک `StorefrontLayoutVersion(status=published)` اولیه باید به‌صورت خودکار (management command یا data migration، مشابه الگوی `seed_industry_templates`) ساخته شود که section هایی معادل بخش‌های *فعلاً فعال* آن فروشگاه در `home.html` را می‌سازد (هیرو موجود، بنرهای موجود، دسته‌های موجود، جدیدترین/پرفروش‌ترین/تخفیف‌دار — که از قبل service-level موجودند).
- لوگو/رنگ‌ها/بنرهای موجود merchant باید عیناً حفظ شوند — **هیچ داده‌ای نباید silently حذف شود**.
- تا زمانی که مهاجرت یک فروشگاه کامل نشده، `home()` باید به رندر مسیر فعلی (hard-coded) fallback کند — یعنی رندر جدید مبتنی بر layout باید *opt-in per store* باشد تا مهاجرت تدریجی و بدون ریسک قطعی انجام شود.

❓ **OPEN DECISION.** آیا مهاجرت باید همه فروشگاه‌ها را یک‌باره به سیستم جدید منتقل کند، یا یک فیچر-فلگ per-store (`Store.uses_visual_layout`) داشته باشیم که مرچنت‌ها تدریجی و داوطلبانه migrate کنند؟ پیشنهاد من گزینه دوم (ایمن‌تر، قابل‌بازگشت) است.

---

## ۲۴. یکپارچگی با قالب‌های صنعتی

💡 **RECOMMENDATION.** هر `IndustryTemplate` (از کار قبلی) می‌تواند یک `default_layout` (ارجاع به یک `StorefrontLayoutVersion` الگو یا یک JSON blueprint) حمل کند. نصب یک قالب صنعتی روی یک Store:
- اگر فروشگاه هنوز چیدمان سفارشی منتشرشده‌ای ندارد → مستقیماً چیدمان پیش‌فرض قالب اعمال می‌شود.
- اگر فروشگاه از قبل چیدمان سفارشی و منتشرشده دارد → **نباید بدون تأیید صریح merchant بازنویسی شود** (طبق الزام دقیق کاربر) — باید یک هشدار/تأیید دو مرحله‌ای مشابه الگوهای تأیید مخرب موجود در پروژه (مثلاً حذف Brand با محصولات وابسته) نمایش داده شود.

---

## ۲۵. مسیرهای URL پیشنهادی

💡 **RECOMMENDATION (نام‌گذاری، نه پیاده‌سازی):**
```
admin-portal/storefront-builder/                      (نمای اصلی ادیتور)
admin-portal/storefront-builder/sections/add/          (POST)
admin-portal/storefront-builder/sections/<id>/edit/    (GET/POST)
admin-portal/storefront-builder/sections/<id>/toggle/  (POST)
admin-portal/storefront-builder/sections/<id>/remove/  (POST)
admin-portal/storefront-builder/sections/reorder/      (POST, x_ids قرارداد)
admin-portal/storefront-builder/header/                (GET/POST)
admin-portal/storefront-builder/footer/                (GET/POST)
admin-portal/storefront-builder/draft/save/            (POST)
admin-portal/storefront-builder/draft/discard/         (POST)
admin-portal/storefront-builder/publish/                (POST)
admin-portal/storefront-builder/versions/               (GET، تاریخچه)
admin-portal/storefront-builder/versions/<id>/restore/  (POST)
admin-portal/storefront-builder/preview/                (GET، فقط staff)
```
همه در `apps/dashboard/urls.py` یا یک namespace جدید `storefront_builder`، هم‌راستا با الگوی مسیرهای موجود `homepage/hero/*`.

---

## ۲۶. سرویس‌های پیشنهادی

💡 **RECOMMENDATION.**
- `apps/storefront_builder/services/layout_service.py` — `get_or_create_draft(store)`, `save_draft(store, sections_data)`, `publish(store)`, `discard_draft(store)`, `restore_version(store, version_id)`.
- `apps/storefront_builder/services/section_registry.py` — تعریف `SectionDefinition` ها و توابع `get_definition(key)`, `list_definitions()`.
- `apps/storefront_builder/services/section_data_service.py` — پل بین section و منابع داده موجود (`storefront_listing_products`, `Category.objects...`).
- `apps/storefront_builder/services/reorder_service.py` — پیاده‌سازی قرارداد `x_ids` موجود برای section ها.

---

## ۲۷. تمپلیت‌ها و ماژول‌های فرانت پیشنهادی

💡 **RECOMMENDATION.**
- `apps/dashboard/templates/dashboard/storefront_builder/editor.html` (صفحه اصلی ادیتور — Alpine component برای مدیریت state پیش‌نمایش/انتخاب دستگاه).
- `apps/dashboard/templates/dashboard/storefront_builder/partials/section_list.html` (همان الگوی drag موجود).
- `apps/dashboard/templates/dashboard/storefront_builder/partials/section_settings_<key>.html` به‌ازای هر نوع section (یا یک تمپلیت پویا per Registry entry).
- `templates/storefront/sections/*.html` — تمپلیت‌های رندر عمومی (سمت storefront) به‌ازای هر section key، جداگانه از تمپلیت‌های تنظیمات ادیتور.
- بدون کتابخانه JS جدید — ادامه Alpine.js + htmx + native drag موجود.

---

## ۲۸. Migrationهای پیشنهادی

💡 **RECOMMENDATION (فهرست مفهومی، اجرا در فاز ۲):**
1. افزودن `store` FK به `HeroSlide`, `PromotionalBanner`, `SocialLink`, `Menu`, `MenuItem`, `ContentPage` (+ data migration برای انتساب رکوردهای فعلی به فروشگاه(های) موجود — نیازمند تصمیم کاربر، به بخش ۳۲ مراجعه شود).
2. مدل‌های جدید: `StorefrontLayout`, `StorefrontLayoutVersion`, `StorefrontSection`.
3. مدل‌های جدید (یا گسترش `FooterSettings`): `StorefrontHeaderConfig` (اگر تصمیم بخش ۱۳ آن را ایجاب کند).
4. Data migration: ساخت نسخه published اولیه به‌ازای هر Store موجود (بخش ۲۳).

---

## ۲۹. استراتژی تست

💡 **RECOMMENDATION.** فهرست کامل در دستور کار فاز ۲ کاربر آمده (کنترل دسترسی، تفکیک مستأجر، ساخت layout/draft، Section Registry، رد section نامعتبر، افزودن/حذف، فعال/غیرفعال، بازچینش، نرمال‌سازی موقعیت تکراری، رد cross-store، مالکیت محصول/دسته، تنظیمات هدر/فوتر، پیش‌نمایش draft، چیدمان منتشرشده عمومی، اتمی بودن انتشار، تاریخچه نسخه، rollback، ایزوله بودن draft‌های ذخیره‌نشده، چیدمان پیش‌فرض صنعتی، مهاجرت فروشگاه موجود، ساختار تمپلیت موبایل، کش/invalidation) — این ممیزی آن فهرست را تأیید می‌کند و چیز دیگری اضافه نمی‌کند.

---

## ۳۰. استراتژی تأیید در مرورگر

💡 **RECOMMENDATION.** طبق دستور کار فاز ۲ کاربر: باز کردن ادیتور، مشاهده پیش‌نمایش کامل، افزودن هیرو/گرید دسته/محصولات ویژه، بازچینش با drag و با دکمه fallback، غیرفعال/فعال‌سازی مجدد، ویرایش بنر/هدر/فوتر، سوییچ دستگاه پیش‌نمایش، ذخیره draft، تأیید عدم‌تغییر storefront عمومی، پیش‌نمایش draft، انتشار، تأیید تغییر storefront عمومی، ساخت و discard یک draft دیگر، بازگردانی نسخه قبلی، تأیید بدون اسکرول افقی در 390px، اسکرین‌شات‌های منتخب.

---

## ۳۱. فازهای پیاده‌سازی

💡 **RECOMMENDATION.** توالی ۱۶-کامیتی که کاربر در دستور کار مشخص کرده (مدل‌ها/migration → Registry → سرویس چیدمان/نسخه → پیش‌نمایش/انتشار → UI پایه ادیتور → drag/ordering → هدر → فوتر → بنر/هیرو → محصول → دسته/برند → سایر section ها → واکنش‌گرا → یکپارچگی صنعتی → مهاجرت فروشگاه‌های موجود → تست/رفع باگ مرورگر) به‌طور کامل با معماری پیشنهادی این گزارش سازگار است و بدون تغییر پذیرفته می‌شود.

---

## ۳۲. ریسک‌ها و تصمیمات باز (جمع‌بندی همه ❓ OPEN DECISION های این سند)

1. آیا هدر/فوتر بخشی از همان نسخه‌بندی چیدمان صفحه اصلی باشند یا پیکربندی جدا (بخش ۱۳)؟
2. آیا restore نسخه قبلی مستقیم منتشر شود یا ابتدا draft بسازد (بخش ۱۴)؟
3. آیا مهاجرت فروشگاه‌های موجود یک‌باره باشد یا با فیچر-فلگ تدریجی per-store (بخش ۲۳)؟
4. مجوز جدید (`STOREFRONT_LAYOUT_MANAGE`) ساخته شود یا از `CONTENT_MANAGE` موجود استفاده شود (بخش ۱۹)؟
5. آیا rate limiting باید به عملیات reorder/publish اضافه شود، در حالی که هیچ الگوی مشابهی در پروژه فعلی وجود ندارد (بخش ۲۰)؟
6. **مهم‌ترین تصمیم باز**: مدل‌های global موجود (`HeroSlide` و غیره) چگونه به store-scoped تبدیل شوند — آیا داده فعلی (که ظاهراً برای یک فروشگاه توسعه/دمو نوشته شده) به یک Store خاص نسبت داده شود، یا برای هر Store کپی/reset شود؟ این یک تصمیم داده‌ای حساس است که باید صریحاً توسط کاربر تأیید شود پیش از نوشتن هر data migration.

---

## ۳۳. برنامه اجرای دقیق پیشنهادی

💡 **RECOMMENDATION.** به‌طور خلاصه: ابتدا رفع شکاف store-scoping در `apps/content` (پیش‌نیاز حیاتی، بخش ۸/۳۲)، سپس مدل‌های گزینه C (بخش ۱۰)، سپس Section Registry (بخش ۱۲)، سپس سرویس‌های چیدمان/نسخه/انتشار (بخش ۱۴)، سپس UI ادیتور با استفاده مجدد از الگوی drag موجود (بخش ۱۶)، سپس اتصال تدریجی section types به داده واقعی (بخش ۱۸)، سپس مهاجرت فروشگاه‌های موجود (بخش ۲۳) با فیچر-فلگ ایمن، در نهایت یکپارچگی با قالب‌های صنعتی (بخش ۲۴). این پیشنهاد دقیقاً با توالی ۱۶-کامیتی کاربر (بخش ۳۱) هم‌راستاست.

---

## ۳۴. فایل‌های برآوردی که در فاز ۲ تغییر خواهند کرد

💡 **RECOMMENDATION (برآورد، نه فهرست قطعی):**
- جدید: ~۱۵-۲۵ فایل در یک اپ جدید `apps/storefront_builder` (مدل‌ها، migrationها، سرویس‌ها، view‌ها، URLها، تمپلیت‌های ادیتور، تست‌ها).
- جدید: ~۱۴+ تمپلیت رندر section (`templates/storefront/sections/*.html`).
- تغییریافته: `apps/content/models.py` (افزودن `store` FK)، migration جدید مرتبط، `apps/content/README.md` (به‌روزرسانی مستندسازی).
- تغییریافته: `apps/catalog/views.py` (`home()` — مسیر انشعابی به رندر جدید، پشت فیچر-فلگ).
- تغییریافته: `apps/dashboard/urls.py`, `apps/dashboard/views.py` (مسیرها/ویوهای هیرو/بنر موجود ممکن است به اپ جدید منتقل یا wrap شوند).
- تغییریافته احتمالی: `apps/stores/authorization.py` (مجوز جدید، در صورت تصمیم بخش ۳۲.۴).
- بدون تغییر: `apps/orders`, `apps/checkout`, `apps/shipping`, `apps/tax`, تنظیمات دامنه/SMS (طبق محدودیت صریح دامنه کار).

---

## ۳۵. استراتژی بازگشت (Rollback Strategy)

💡 **RECOMMENDATION.**
- تمام کار فاز ۲ در شاخه جداگانه (`claude/rastisi-storefront-visual-builder`) نگه داشته می‌شود — بازگشت یعنی merge نکردن آن شاخه.
- Migrationها مستند و به‌ترتیب معکوس قابل‌برگشت‌اند (افزودن FK/مدل جدید — بدون حذف/تغییر مخرب فیلد موجود).
- رندر جدید صفحه اصلی پشت یک فیچر-فلگ per-store قرار می‌گیرد (بخش ۲۳) — یعنی حتی پس از merge، غیرفعال کردن فلگ فوراً فروشگاه را به رفتار قدیمی (hard-coded) بازمی‌گرداند بدون نیاز به rollback کد.
- کامیت‌ها منطقی و اتمی هستند (۱۶ کامیت مجزا طبق بخش ۳۱) — هر کامیت به‌تنهایی قابل `revert` است.
- سازگاری فروشگاه‌های موجود در تمام مراحل حفظ می‌شود (بخش ۲۳) — یعنی حتی نیمه‌کاره ماندن فاز ۲ باعث خرابی storefront فعلی نمی‌شود.

---

## پیوست: ماتریس واقعیت در برابر توصیه (خلاصه شفافیت)

طبق الزام صریح این ممیزی («گزارش باید به‌روشنی واقعیت‌های یافت‌شده در مخزن، توصیه‌های معماری، و تصمیمات حل‌نشده را از هم جدا کند»):

- بخش‌های ۱ تا ۹ عمدتاً **FACT** (با استثنائات نشان‌داده‌شده) — یافته‌های مستقیم کد با ارجاع `file:line`.
- بخش‌های ۱۰ تا ۳۱، ۳۳ تا ۳۵ عمدتاً **RECOMMENDATION** — پیشنهادهای معماری من، هنوز پیاده‌سازی‌نشده.
- بخش ۳۲ به‌طور کامل **OPEN DECISION** — نیازمند تأیید صریح کاربر پیش از شروع فاز ۲.

**هیچ‌کدام از پیشنهادهای این گزارش تاکنون پیاده‌سازی نشده‌اند. این سند فقط یک گزارش است.**
