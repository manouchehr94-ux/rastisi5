# گزارش ممیزی وضعیت فعلی: قالب فروشگاه، پریست، سازنده بصری و کالکشن‌های مرچنت

**فاز:** ممیزی و معماری (Phase 1) — فقط بررسی و گزارش، بدون تغییر رفتار برنامه.

**شاخه:** `claude/rastisi-storefront-builder-audit-8q2vyc`
**کامیت پایه:** `d830f5f` — "product-entry: final verified fixes"
**تاریخ:** 2026-08-06

این سند طبق الزام صریح فاز ۱ نوشته شده است: **هیچ مدل، migration، view، URL، template، CSS یا JavaScript‌ای در این کامیت تغییر نکرده است.** تنها تغییر مخزن همین سه فایل گزارش (`docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_*.md`) است.

> **راهنمای خواندن سند:** هر بخش با یکی از سه برچسب مشخص می‌شود:
> - 🔍 **FACT** — واقعیتی که مستقیماً در کد یافت شده (با ارجاع `file:line`).
> - 💡 **RECOMMENDATION** — پیشنهاد معماری، به گزارش خواهرِ این سند (`STOREFRONT_TEMPLATE_AND_BUILDER_ARCHITECTURE_PLAN.md`) موکول شده.
> - ❓ **OPEN DECISION** — تصمیمی که باید توسط کاربر گرفته شود.

> ⚠️ **نکته حیاتی درباره سند مرجع قدیمی‌تر.** یک ممیزی قبلی (`docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md`، تاریخ 2026-08-03، کامیت پایه `72b1034`) وجود دارد که در آن زمان **هیچ‌کدام** از قابلیت‌های سازنده بصری پیاده‌سازی نشده بود. از آن تاریخ تاکنون، طبق تاریخچه Git (`git log --oneline -- apps/storefront_builder`)، **۱۰ کامیت شامل ۱۷ چک‌پوینت** دقیقاً طبق توصیه‌های همان گزارش پیاده‌سازی شده‌اند. این سند وضعیت **واقعی و فعلی** کد را (نه توصیه‌های آن گزارش قدیمی را) گزارش می‌دهد. همچنین سند `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` (بخش‌های ۱۱.۸/۱۱.۹) که Page Builder را همچنان «ناقص» توصیف می‌کند **قدیمی و منسوخ** است — آن سند باید در فاز بعدی به‌روزرسانی شود (به بخش ۱۴ این گزارش مراجعه شود).

---

## ۱. خلاصه مدیریتی (Executive Summary)

🔍 **FACT.** برخلاف فرض اولیه («یک فروشگاه‌ساز که هنوز سازنده بصری ندارد»)، این مخزن از قبل یک اپ کامل و تست‌شده به نام `apps/storefront_builder` دارد که معماری Draft/Publish/Version/Section Registry/Rollback را برای **چیدمان بخش‌های صفحه اصلی + هدر + فوتر** پیاده‌سازی کرده است (۷ فایل سرویس/مدل/رجیستری، ۷ فایل تست با ۱۱۸۴ خط، ۱۶ نوع section، ۱۷ endpoint). صفحه اصلی عمومی (`apps/catalog/views.py:42-118`) از قبل به این سیستم متصل است و پشت یک فیچر-فلگ per-store (`StorefrontLayout.uses_visual_storefront_layout`) کار می‌کند.

🔍 **FACT.** آنچه در این مخزن **وجود ندارد** دقیقاً همان چیزی است که در خواسته کاربر برجسته است و در سیستم فعلی نیست: (۱) تعویض **قالب بصری کامل سایت** (نه فقط section homepage) — یعنی تغییر خانواده Header/Footer/Card-style/رنگ‌بندی به‌عنوان یک بسته واحد؛ (۲) **کالکشن مرچنت‌ساخته** به‌عنوان یک مدل مستقل (فقط `ProductTag` با `purpose="collection"` وجود دارد که فاقد تصویر/SEO/ترتیب دستی محصول است)؛ (۳) **سیستم Preset** (رنگ+فونت+فاصله+border-radius+انیمیشن به‌صورت بسته) — چیزی که امروز وجود دارد فقط ۶ پریست رنگی مستقل از فونت/فاصله است؛ (۴) تنظیمات **Responsive per-section**؛ (۵) لایه **کش** روی رندر storefront.

🔍 **FACT — یافته مهم.** یک الگوی معماری بسیار نزدیک به «Template + Version + Installation + Safe Update + Rollback-capable History» **از قبل به‌طور کامل پیاده‌سازی شده** اما محدود به **تاکسونومی کاتالوگ** (دسته‌بندی/ویژگی/schema)، نه ظاهر بصری: `IndustryTemplate`/`StoreIndustryInstallation`/`StoreTemplateUpdate` (`apps/catalog/models.py:1332-1801`). این الگو دقیقاً همان چیزی است که معماری «تعویض قالب بصری» پیشنهادی این گزارش (سند خواهر) باید از آن الگو بگیرد — نه کد آن را.

💡 **نتیجه‌گیری خلاصه.** فاز بعدی نباید یک سازنده بصری از صفر بسازد (از قبل وجود دارد و کار می‌کند)، بلکه باید: (۱) یک لایه «Template Definition + Preset» **جدید و مستقل** از `IndustryTemplate` (که نقش متفاوتی دارد) روی بالای `StorefrontLayoutVersion` موجود اضافه کند، (۲) یک مدل `MerchantCollection` مستقل از `ProductTag` بسازد، (۳) `SectionDefinition`/`StorefrontSection.settings` را برای پشتیبانی از Data Source (شامل کالکشن) و تنظیمات Responsive گسترش دهد، (۴) شکاف‌های امنیتی/کارایی باقی‌مانده (کش، تکرار تمپلیت پوسته بین preview/storefront) را ببندد.

---

## ۲. معماری فعلی — سازنده بصری صفحه اصلی (`apps/storefront_builder`)

### ۲.۱ مدل‌ها

🔍 **FACT.** سه مدل در `apps/storefront_builder/models.py`:

- **`StorefrontLayout`** (`models.py:49-86`) — لنگر یک‌به‌یک هر Store (`store = OneToOneField("stores.Store", ..., related_name="storefront_layout")`, خط ۵۶-۵۹)، با `uses_visual_storefront_layout` (فیچر-فلگ per-store، خط ۶۰-۶۳)، `published_version`/`draft_version` (دو FK جدا به `StorefrontLayoutVersion`، خط ۶۴-۷۱). متد `provision_for(store)` (خط ۸۰-۸۶) idempotent است.
- **`StorefrontLayoutVersion`** (`models.py:89-170`) — نسخه‌ی immutable-پس‌از-انتشار چیدمان کامل. `Status` = `DRAFT`/`PUBLISHED`/`ARCHIVED` (خط ۹۸-۱۰۱). `Source` = `MANUAL`/`LEGACY_BOOTSTRAP`/`INDUSTRY_TEMPLATE`/`RESTORED` (خط ۱۰۳-۱۰۷). **هدر و فوتر مستقیماً روی همین مدل هستند** (`header_config`/`footer_config` JSONField، خط ۱۲۲-۱۲۳) — یعنی همان چرخه Draft/Publish صفحه اصلی را به‌اشتراک می‌گذارند (نه یک نسخه‌بندی جدا). `content_fingerprint` (SHA-256، خط ۱۲۵-۱۲۸) و `compute_fingerprint()` (خط ۱۵۸-۱۷۰) برای تشخیص drift مستقل از ترتیب ذخیره‌سازی. `UniqueConstraint(["layout","version_number"])` (خط ۱۴۰-۱۴۳).
- **`StorefrontSection`** (`models.py:173-197`) — `section_key` (`CharField`, بدون choices در دیتابیس — allowlist در سرویس، خط ۱۸۵)، `order` (خط ۱۸۶)، `is_active` (تنها بولین فعال/غیرفعال، خط ۱۸۷)، `settings` (JSONField، خط ۱۸۸).

🔍 **FACT — چندنمونه‌ای بودن Section از قبل پشتیبانی می‌شود.** هیچ `UniqueConstraint` روی `section_key` وجود ندارد؛ شناسه واقعی instance همان `id` (Primary Key) است، نه `section_key`. یعنی دقیقاً همان مدلی که کاربر در بخش ۶ درخواست کرده (تفکیک `section_type` از `section_instance_id`) از قبل با `section_key` + `id` پیاده‌سازی شده است.

### ۲.۲ Section Registry

🔍 **FACT.** `apps/storefront_builder/section_registry.py` یک دیکشنری پایتونی ثابت (`SECTION_REGISTRY`, خط ۹۶-۱۹۴) با **۱۶ نوع section** فعلاً ثبت‌شده (نه ۲۵ نوع کامل خواسته‌شده در بخش ۵ کار کاربر):

| کلید | برچسب فارسی | max_instances | duplicable | has_settings_form |
|---|---|---|---|---|
| `announcement_bar` | نوار اعلان | 1 | خیر | خیر |
| `hero_banner` | بنر هیرو | 1 | خیر | خیر |
| `image_slider` | اسلایدر تصویر | نامحدود | بله | خیر |
| `single_banner` | بنر تکی | نامحدود | بله | خیر |
| `multi_banner` | ردیف چند بنری | نامحدود | بله | خیر |
| `category_grid` | گرید دسته‌بندی | نامحدود | بله | خیر |
| `featured_products` | محصولات ویژه | نامحدود | بله | خیر |
| `newest_products` | جدیدترین محصولات | نامحدود | بله | خیر |
| `best_sellers` | پرفروش‌ترین‌ها | نامحدود | بله | خیر |
| `discounted_products` | محصولات تخفیف‌دار | نامحدود | بله | خیر |
| `amazing_offers` | پیشنهادهای شگفت‌انگیز | نامحدود | بله | خیر |
| `brand_carousel` | کاروسل برندها | نامحدود | بله | خیر |
| `promo_cards` | کارت‌های تبلیغاتی | نامحدود | بله | خیر |
| `rich_text` | متن غنی | نامحدود | بله | **بله** |
| `image_text` | متن و تصویر | نامحدود | بله | **بله** |
| `trust_features` | ردیف اعتماد و ویژگی‌ها | 1 | خیر | خیر |

منبع: `section_registry.py:96-194`، تأییدشده مستقل با `test_section_registry.py:11-16` (`EXPECTED_KEYS` — این تست به‌عنوان change-detector عمل می‌کند).

🔍 **FACT — نبود Data Source واقعی.** تمام ۱۶ نوع (به‌جز `rich_text`/`image_text`) از تابع `_passthrough_dict` (`section_registry.py:43-47`) برای اعتبارسنجی استفاده می‌کنند که فقط چک می‌کند ورودی یک شیء JSON است — **بدون schema واقعی برای `data_source`، `item_limit`، `ordering`، `desktop_columns` و مشابه.** این دقیقاً محدودیتی است که در کامنت خودِ فایل هم اذعان شده: «تعاریف کامل settings-schema هر کلید در چک‌پوینت‌های ۱۱ تا ۱۴ اضافه می‌شود» (`section_registry.py:92-95`) — یعنی معماران قبلی خودشان این را به‌عنوان کار باقی‌مانده مستند کرده‌اند.

🔍 **FACT.** `featured_products` در عمل هیچ منبع داده مستقلی ندارد — `render_service.py` آن را مستقیماً به `_newest_products_context` معادل می‌گیرد چون فیلد `Product.is_featured` در دیتابیس وجود ندارد (کامنت در `render_service.py:97-101`).

### ۲.۳ سرویس‌های چرخه‌ی Draft/Preview/Publish/Rollback

🔍 **FACT.** `apps/storefront_builder/services/layout_service.py` (۲۳۱ خط) این توابع را دارد (تمام موارد داخل `@transaction.atomic`):

- `get_or_create_draft(store, *, user=None)` (خط ۷۶-۱۱۰) — کلون از published؛ اگر اولین نسخه‌ی این Store باشد، از `bootstrap_service.apply_bootstrap_content` استفاده می‌کند (بازسازی صفحه اصلی قدیمی به‌عنوان section، نه صفحه خالی).
- `publish(store, *, user=None)` (خط ۱۲۵-۱۵۳) — Rate-limited (۲۰ بار در ساعت، خط ۲۹-۳۱)؛ **فقط اشاره‌گر `published_version_id` را عوض می‌کند** (اتمیک)، نسخه‌ی قبلی را `ARCHIVED` می‌کند، `content_fingerprint` را محاسبه/ذخیره می‌کند، و **تنها همین‌جا** `layout.uses_visual_storefront_layout = True` تنظیم می‌شود (خط ۱۵۱) — یعنی فیچر-فلگ فقط با اولین Publish صریح فعال می‌شود، نه با ساخت Draft.
- `discard_draft(store)` (خط ۱۱۳-۱۲۲) — فقط اشاره‌گر Draft را پاک/حذف می‌کند؛ published دست‌نخورده می‌ماند.
- `restore_version(store, version_id, *, user=None)` (خط ۱۶۲-۱۹۱) — **هرگز مستقیماً منتشر نمی‌کند**؛ یک Draft جدید با `source=RESTORED` می‌سازد؛ ارجاع cross-store به `CrossStoreVersionError` منجر می‌شود (fail-closed، هم برای ID خارجی و هم ناموجود).
- `apply_industry_layout(store, industry_template, *, user=None, force=False)` (خط ۱۹۴-۲۳۱) — پل بین `IndustryTemplate.default_section_keys` و چیدمان صفحه اصلی؛ اگر از قبل published دارد، بدون `force=True` رد می‌شود (`StorefrontAlreadyPublishedError`) — دقیقاً همان محافظت «بدون تأیید صریح overwrite نشود» که در گزارش قبلی توصیه شده بود (`STOREFRONT_VISUAL_BUILDER_AUDIT.md:406`).

🔍 **FACT.** Rate limiting با زیرساخت عمومی و از‌قبل‌موجود `apps.core.services.rate_limit.enforce_rate_limit` (`apps/core/services/rate_limit.py:19-30`) پیاده‌سازی شده — همان زیرساختی که در `apps/sms`/`apps/portal` هم استفاده می‌شود؛ **یک زیرساخت جدید ساخته نشده.**

### ۲.۴ Renderer مشترک

🔍 **FACT — الزام «رندرر مشترک» کاربر (بخش ۱۳ کار او) از قبل برآورده شده، با یک استثنای مستند‌شده.** `apps/storefront_builder/services/render_service.py` (۱۷۳ خط) تابع `build_render_items(version, store)` (خط ۱۳۸-۱۷۲) را دارد که «تنها نقطه اشتراک بین پیش‌نمایش ادیتور (Draft) و صفحه اصلی عمومی (published)» است — کامنت صریح در بالای فایل (خط ۱-۱۳). این تابع:
- روی `version.sections.filter(is_active=True).order_by("order","id")` تکرار می‌کند (خط ۱۵۵)،
- کلید نوع section ناشناخته را بی‌صدا نادیده می‌گیرد (خط ۱۵۶-۱۵۹) — یعنی حذف یک section type از Registry هرگز صفحه عمومی را نمی‌شکند،
- یک کش per-request per-section-key (خط ۱۵۴، ۱۶۰-۱۶۳) دارد تا چند نمونه از یک نوع (مثلاً دو `newest_products`) کوئری تکراری نزنند — تست‌شده مستقیم در `test_render_service.py:65-91`.

هر دو مسیر مصرف‌کننده — `apps/catalog/views.py:home()` (published) و `apps/storefront_builder/views.py::storefront_preview` (draft) — از همین تابع با یک آرگومان متفاوت (`published` در برابر `draft`) صدا می‌زنند.

🔍 **FACT — نقص باقیمانده در رندرر مشترک (تکرار پوسته صفحه).** برخلاف بدنه section‌ها (که کاملاً مشترک است — هر دو مسیر از همان ۱۶ فایل `apps/storefront_builder/templates/storefront_builder/sections/*.html` استفاده می‌کنند)، **پوسته صفحه (هدر/ناوبری/فوتر HTML)** بین دو فایل template مستقل و **دستی-کپی‌شده** تکرار شده است: `apps/storefront_builder/templates/storefront_builder/preview.html` (۱۳۵ خط، فقط برای staff) در برابر `apps/catalog/templates/catalog/home_visual.html` (۲۱۱ خط، عمومی). این دو نه یکسان‌اند (مثلاً `preview.html` فرم جستجو و لینک سبد/علاقه‌مندی را غیرفعال/placeholder می‌کند چون پیش‌نمایش staff است، در حالی که `home_visual.html` این‌ها را واقعی رندر می‌کند؛ `home_visual.html` یک مگامنوی دسته‌بندی و مودال ورود دارد که `preview.html` فاقد آن است) و نه از یک partial مشترک include می‌شوند — منطق مصرف `effective_header_config()`/`effective_footer_config()` در هر دو فایل جداگانه دستی تکرار شده. این یک ریسک واقعی «تفاوت Preview و Storefront» است که دقیقاً همان چیزی است که کاربر در بخش ۱۳ کار خود صریحاً نگرانش بوده.

### ۲.۵ Endpointها و View

🔍 **FACT.** `apps/storefront_builder/urls.py` **وجود ندارد** — تمام مسیرها مستقیماً در `apps/dashboard/urls.py:200-216` رجیستر شده‌اند و به `apps/storefront_builder/views.py` (۳۷۴ خط) اشاره می‌کنند. جدول کامل ۱۷ endpoint (همه پشت `@staff_required` + `@permission_required(STOREFRONT_LAYOUT_MANAGE)`):

| مسیر | نام | نقش |
|---|---|---|
| `storefront-builder/` | editor | صفحه اصلی ادیتور |
| `storefront-builder/preview/` | preview | پیش‌نمایش تمام‌صفحه Draft (`@xframe_options_sameorigin`) |
| `storefront-builder/sections/` | section-list | partial htmx |
| `storefront-builder/sections/add/` | section-add | افزودن (چک `max_instances`) |
| `storefront-builder/sections/reorder/` | section-reorder | بازچینش دسته‌جمعی |
| `storefront-builder/sections/<id>/settings/` | section-settings | فرم تنظیمات (فقط `has_settings_form=True`) |
| `storefront-builder/sections/<id>/remove/` | section-remove | حذف (چک `removable`) |
| `storefront-builder/sections/<id>/toggle/` | section-toggle | فعال/غیرفعال |
| `storefront-builder/sections/<id>/duplicate/` | section-duplicate | تکثیر (چک `duplicable`) |
| `storefront-builder/sections/<id>/move/` | section-move | بالا/پایین (fallback موبایل/کیبورد) |
| `storefront-builder/header/` | header | ویرایش `header_config` |
| `storefront-builder/footer/` | footer | ویرایش `footer_config` |
| `storefront-builder/publish/` | publish | انتشار |
| `storefront-builder/discard/` | discard | دورانداختن Draft |
| `storefront-builder/apply-industry-layout/` | apply-industry-layout | اعمال چیدمان صنف |
| `storefront-builder/history/` | history | تاریخچه نسخه‌ها |
| `storefront-builder/history/<id>/restore/` | restore | بازگردانی |

منبع: `apps/dashboard/urls.py:200-216` + `apps/storefront_builder/views.py` (شماره خط دقیق هر view در ضمیمه اجراشده توسط عامل تحقیق، در دسترس روی درخواست).

🔍 **FACT.** `_get_scoped_section(request, pk)` (`storefront_builder/views.py:117-122`) الگوی محافظتی جالب توجهی دارد: نه فقط `store=` بلکه `version__status=DRAFT` هم شرط است — یعنی endpointهای ویرایش section **هرگز** حتی نمی‌توانند نسخه published/archived را دست بزنند، صرف‌نظر از باگ‌های احتمالی در فراخوانی.

### ۲.۶ Drag-and-drop

🔍 **FACT.** الگوی موجود در بقیه پروژه (`apps/dashboard/templates/dashboard/partials/product_images_list.html:5-21` و `brands_table.html:25-69`) — Alpine.js `x-data`، HTML5 native `draggable`/`dragover.prevent`/`drop.prevent`، POST لیست idهای `htmx.ajax`، **به‌همراه دکمه‌های fallback بالا/پایین** (`brands_table.html:52-69`) — عیناً برای section builder هم تکرار شده (`storefront_section_reorder` + `storefront_section_move`، بخش ۲.۵ بالا). یعنی الزام صریح کاربر («بازچینش فقط با موس کافی نیست») **از قبل برآورده شده.**

⚠️ **FACT — نکته دقتِ لازم برای الگوهای مشابه آینده.** سرویس‌های reorder موجود در بقیه پروژه (`reorder_product_images`، `apps/catalog/services/product_image_service.py:176-187`؛ `reorder_brands`، `apps/catalog/services/brand_service.py:100-113`) داخل `@transaction.atomic` **نیستند** — با اینکه گزارش قبلی ادعا کرده بود این الگو «همیشه در یک تراکنش انجام می‌شود». این ادعا در آن گزارش نادقیق بوده؛ یک مدل جدید (مثلاً بازچینش کالاهای کالکشن) باید صراحتاً `@transaction.atomic` را خودش اضافه کند، نه فرض کند از الگوی موجود به ارث می‌رسد.

### ۲.۷ مهاجرت فروشگاه‌های موجود (Bootstrap)

🔍 **FACT.** `apps/storefront_builder/services/bootstrap_service.py` (۹۵ خط) دقیقاً همان الگوریتم توصیه‌شده در گزارش قبلی را پیاده‌سازی کرده: `build_bootstrap_sections(store)` (خط ۲۳-۵۳) صفحه اصلی hard-coded فعلی هر Store را به یک لیست section معادل تبدیل می‌کند (`hero_banner` فقط اگر `HeroSlide` فعال دارد، `discounted_products` فقط اگر محصول تخفیف‌دار دارد، و غیره) — **هیچ داده‌ای حذف نمی‌شود.** `apps.catalog.views.home()` تا وقتی `uses_visual_storefront_layout=True` **و** `published_version` موجود نباشد، همچنان به `catalog/home.html` قدیمی fallback می‌کند (`apps/catalog/views.py:56،61-71`، تست یکپارچه در `test_public_homepage_integration.py:31-51`).

### ۲.۸ تست‌ها

🔍 **FACT.** ۷ فایل تست، ۱۱۸۴ خط: `test_models.py`(۱۱۴)، `test_layout_service.py`(۳۱۰)، `test_bootstrap_service.py`(۱۴۹)، `test_public_homepage_integration.py`(۸۷)، `test_render_service.py`(۱۰۹)، `test_section_registry.py`(۶۲)، `test_views.py`(۳۵۳). موارد کلیدی پوشش‌داده‌شده: ایزوله‌سازی cross-store در همه سطوح (مدل/سرویس/view)، عدم درز Draft فروشگاه دیگر در preview (`test_views.py`، عبارت مارکر `"SECRET-STORE-A-TEXT"`)، عدم انعکاس تغییرات منتشرنشده در صفحه عمومی (مارکر `"PUBLIC-SHOULD-NEVER-SEE-THIS-DRAFT-MARKER"`)، اتمیک بودن Publish، آرشیو نسخه قبلی، rate limit، رد section نوع ناشناخته بدون کرش صفحه عمومی، حفظ `False` صریح در `effective_header_config` (نه falsy-override با `|default:True`).

---

## ۳. آنچه در سازنده بصری فعلی **غایب** است (نسبت به خواسته کامل کاربر)

🔍 **FACT — جستجوی مستقیم، هر مورد با الگوی جستجو ذکرشده:**

| قابلیت خواسته‌شده | وضعیت | شواهد |
|---|---|---|
| `collapsed_in_editor` مستقل از `enabled_on_storefront` | ❌ ABSENT | فقط `is_active` یکی (`models.py:187`)؛ `grep -rn "collapsed_in_editor\|enabled_on_storefront"` صفر نتیجه |
| Preview link/token قابل‌اشتراک | ❌ ABSENT | preview فقط session-authenticated staff (`views.py::storefront_preview`)؛ `grep -rni "preview_token"` صفر نتیجه |
| Autosave | ❌ ABSENT | `grep -rni "autosave"` صفر نتیجه؛ همه ذخیره‌ها POST همزمان صریح‌اند |
| Undo/Redo | ❌ ABSENT | `grep -rni "undo\|redo"` صفر نتیجه واقعی (فقط false-positive از "StoreDomain") |
| Scheduled Publish | ❌ ABSENT | `published_at` فقط زمان واقعی انتشار را ثبت می‌کند، نه زمان‌بندی آینده؛ بدون Celery/cron |
| تنظیمات Responsive per-section (ستون دسکتاپ/تبلت/موبایل، نمایش/عدم‌نمایش per-device) | ❌ ABSENT | `grep -rni "desktop\|tablet\|mobile\|breakpoint\|columns"` در `section_registry.py`/`models.py` صفر نتیجه |
| Data Source واقعی per section (کالکشن/دسته/برند/تخفیف/دستی) | ⚠️ PARTIAL | فقط سه data source hard-coded هر کدام در یک context builder جدا (`render_service.py:26-115`)؛ بدون فیلد `data_source` قابل‌انتخاب در `settings` |
| کالکشن مرچنت‌ساخته (مستقل) | ⚠️ PARTIAL/CONFLICTING | فقط `ProductTag(purpose="collection")` — به بخش ۵ مراجعه شود |
| تعویض قالب بصری کامل (رنگ+فونت+هدر/فوتر خانواده+کارت) | ❌ ABSENT | فقط `apply_industry_layout` (فقط section ordering، نه رنگ/فونت/هدر خانواده) |
| Preset (رنگ+فونت+spacing+radius+انیمیشن به‌صورت بسته) | ⚠️ PARTIAL | فقط ۶ پریست رنگی (`theme_presets.py`)؛ بدون فونت/spacing/radius/انیمیشن در کل کدبیس |
| کش رندر storefront | ❌ ABSENT | بدون `CACHES` سفارشی، بدون `cache_page` در هیچ view — بدون تغییر نسبت به ممیزی 2026-08-03 |
| رندرر مشترک preview/storefront (بدنه section) | ✅ EXISTS | `render_service.build_render_items` — بخش ۲.۴ |
| رندرر مشترک preview/storefront (پوسته صفحه: هدر/فوتر HTML) | ⚠️ PARTIAL | دو فایل تمپلیت مستقل، منطق تکراری — بخش ۲.۴ |

---

## ۴. سیستم قالب/پریست موجود — `IndustryTemplate`

🔍 **FACT.** یک سیستم بسیار پخته‌تر از حد انتظار در `apps/catalog/models.py:1332-1801` وجود دارد اما دامنه آن **کاملاً متفاوت** از خواسته کاربر است:

- **`IndustryTemplate`** (خط ۱۳۳۲-۱۴۰۶): پلتفرم‌محور، نسخه‌بندی‌شده با `UniqueConstraint(slug, version)` (خط ۱۳۹۷-۱۳۹۹)، `readiness` (draft/validation_failed/review_required/**production_ready**/deprecated/archived، خط ۱۳۳۹-۱۳۴۹) — فقط `production_ready` قابل نصب است. `content_fingerprint` (SHA-256، خط ۱۳۷۹-۱۳۸۲). `default_section_keys` (JSONField، خط ۱۳۸۳-۱۳۹۱) — **این همان فیلدی است که به `storefront_builder` پل می‌زند** (بخش ۲.۷).
- **`StoreIndustryInstallation`** (خط ۱۵۶۹-۱۵۹۷): `store = OneToOneField(..., on_delete=CASCADE)` — **هر Store فقط یک‌بار در کل عمرش می‌تواند نصب کند** (اجرا در `can_install_industry_template`، `apps/catalog/services/industry_template_service.py:35-41`).
- **`StoreTemplateUpdate`** (خط ۱۷۴۴-۱۸۰۱): تاریخچه به‌روزرسانی امن (فقط additive خودکار، بقیه نیازمند بازبینی — سیاست سه‌سطحی `safe_additive`/`review_required`/`blocked`)؛ `clean()` (خط ۱۷۸۹-۱۸۰۱) صراحتاً `from_template.slug == target_template.slug` را اجرا می‌کند — یعنی **تعویض بین خانواده صنف دیگر پشتیبانی نمی‌شود.**

🔍 **FACT — نتیجه‌گیری حیاتی.** `install_industry_template`/`apply_template_update` (`apps/catalog/services/industry_template_service.py:44-162`, `template_update_service.py:182-339`) **فقط** `Category`/`Attribute`/`AttributeValue`/`CategoryAttributeSchema`/`CategoryRecommendedOption` را لمس می‌کنند — هرگز `Product`، `Order`، `Customer`، `ShopSettings` (رنگ/فونت) یا `StorefrontLayout*` (چیدمان/هدر/فوتر) را تغییر نمی‌دهند.

🔍 **FACT — سند تأیید محدودیت به زبان خودِ پروژه.** ADR-25 (`docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md:1381-1384`) صراحتاً می‌نویسد: *«فروشگاهی که صنف اشتباه نصب کرده، یا کسب‌وکارش کاملاً صنف عوض کرده، در این فاز هیچ مسیر پشتیبانی‌شده‌ای برای تعویض در محصول ندارد — اپراتور پلتفرم باید مستقیماً دخالت کند (مثلاً از طریق Django admin) — این یک محدودیت واقعی و نام‌گذاری‌شده است، نه یک سهو.»*

💡 **نتیجه معماری برای سند خواهر.** `IndustryTemplate` **الگوی قابل‌استفاده مجدد** است (نسخه‌بندی immutable با `(slug, version)`، `content_fingerprint`، deep-copy-نه-لینک، سیاست به‌روزرسانی سه‌سطحی) اما **مدل خودش قابل استفاده مجدد نیست** — یک `StorefrontTemplateDefinition`/`StorefrontPreset` کاملاً جدا باید ساخته شود که این الگوها را برای دامنه‌ی متفاوت (ظاهر بصری، نه تاکسونومی) تکرار کند. به بخش ۳ سند معماری مراجعه شود.

---

## ۵. تم/برندینگ — `ShopSettings` و `theme_presets.py`

🔍 **FACT.** `apps/core/models.py:38-221` — مدل `ShopSettings` یک ردیف به‌ازای هر Store (`OneToOneField`) با ۴ دسته فیلد نامرتبط در یک مدل (هویت/تماس، مالیات/ارسال، پیامک، **برندینگ**). فیلدهای برندینگ (خط ۱۳۵-۱۵۰): `logo`/`favicon` (ImageField)، ۷ رنگ hex (`primary_color`, `accent_color`, `secondary_color`, `background_color`, `surface_color`, `text_color`, `muted_text_color`). **هیچ فیلد فونت/spacing/border-radius/animation در کل `apps/core/models.py` وجود ندارد** (تأیید با grep، صفر نتیجه).

🔍 **FACT.** `apps/core/theme_presets.py` — دقیقاً **۶ پریست ثابت** (`digital-purple`, `rose-pink`, `emerald-green`, `honey-amber`, `turquoise`, `crimson-red`؛ خط ۱۳-۱۹)، هرکدام فقط ۴ رنگ (`primary`, `secondary`, `accent`, `background`) — بدون فونت. اعمال می‌شود از طریق `apps/dashboard/forms.py` (`VisualIdentityForm`) و مستقیماً `ShopSettings` را می‌نویسد — **بدون Draft/Publish/Preview/Rollback** برای این بخش (برخلاف چیدمان صفحه که این چرخه را دارد).

🔍 **FACT — سند تصمیم موجود درباره جداسازی `ShopSettings`.** ADR-10 (`SAAS_DOMAIN_DECISIONS.md:333-385`) این ترکیب چهارگانه غیرمرتبط در `ShopSettings` را صراحتاً شناسایی کرده و می‌نویسد که تفکیک برندینگ/تم به یک مدل جداگانه **عمداً به PR آینده موکول شده** («deferred to a dedicated future PR»، خط ۳۶۸-۳۷۰) — یعنی این خودِ پروژه از قبل این نیاز را دیده، اما هنوز اجرا نکرده.

🔍 **FACT.** `Store` (`apps/stores/models.py:31-250`) هیچ فیلد تم/template ندارد — این عمدی و مستند است، مستقیماً در docstring خودِ مدل (خط ۴۰-۴۵): *«این مدل عمداً فیلد owner ندارد ... همچنین فیلدهای billing/subscription/**theme**/payment و دامنه storefront عمومی هم ندارد ...»* — همان ADR‌ای که کامنت بالای `storefront_builder/models.py` (خط ۱۵-۱۹) به آن ارجاع می‌دهد.

---

## ۶. کالکشن‌های مرچنت — وضعیت فعلی

🔍 **FACT.** `Collection`/`ProductCollection` در **هیچ‌جای مخزن وجود ندارد** (`grep "class Collection"`, `grep "class ProductCollection"` — هر دو صفر نتیجه در سراسر `apps/`).

🔍 **FACT — نزدیک‌ترین معادل موجود.** `ProductTag` (`apps/catalog/models.py:1159-1193`) یک مدل Store-owned با فیلد `purpose` است که بین دو حالت سوییچ می‌کند: `general` («برچسبِ عادی») و **`collection`** («مجموعه‌ی فروش (گروهِ دوم)») — خط ۱۱۷۲-۱۱۷۴, ۱۱۸۱. مستقیماً به `Product` از طریق `Product.tags` (M2M ساده، بدون `through`، خط ۲۳۲) وصل است.

🔍 **FACT — محدودیت‌های `ProductTag` نسبت به خواسته کاربر.** فیلدهای موجود فقط `store`, `name`, `code` (Slug)، `purpose`، `is_active` هستند (خط ۱۱۷۶-۱۱۸۲). **موارد زیر در `ProductTag` غایب‌اند:** تصویر کالکشن، توضیحات، SEO (عنوان/توضیح متا)، **ترتیب دستی محصولات درون کالکشن** (چون `Product.tags` یک `ManyToManyField` ساده بدون مدل `through` است — هیچ فیلد order روی رابطه وجود ندارد)، صفحه عمومی مستقل هر کالکشن، پشتیبانی کالکشن هوشمند (شرط‌محور).

🔍 **FACT — هشدار صریح خودِ کد.** Docstring مدل `ProductTag` (خط ۱۱۶۰-۱۱۷۰) عمداً توضیح می‌دهد که `purpose` یک رابطه M2M واحد را برای دو کاربرد متفاوت (تگ جست‌وجو/فیلتر معمولی در برابر «گروه دوم»/مفهوم merchandising-collection) به اشتراک می‌گذارد، و صراحتاً یادآوری می‌کند این **عمداً مستقل از درخت واقعی `Category`** است، نه یک سطح دوم دسته‌بندی.

💡 **نتیجه‌گیری برای سند معماری.** طبق دستور صریح کار کاربر («نام «گروه دوم» یا Tag نباید جایگزین معماری واقعی Collection شود مگر اینکه بررسی کد ثابت کند همان مفهوم است») — این بررسی **نشان می‌دهد `ProductTag` همان مفهوم Collection نیست**: فاقد تصویر/SEO/ترتیب دستی/صفحه مستقل است و اسمش صریحاً «تگ» باقی مانده. بنابراین طبق دستور کاربر، یک مدل `MerchantCollection` **مستقل** باید ساخته شود (نه گسترش `ProductTag`). جزئیات در سند معماری، بخش ۵.

---

## ۷. زیرساخت‌های امنیتی/مجوز قابل استفاده مجدد

🔍 **FACT.** `apps/stores/authorization.py` از قبل یک مجوز اختصاصی برای همین دامنه دارد: **`STOREFRONT_LAYOUT_MANAGE`** (عمداً جدا از `CONTENT_MANAGE`، طبق کامنت‌های ماژول در `apps/storefront_builder/views.py:1-2`) — یعنی سؤال باز شماره ۴ گزارش قبلی (چه مجوزی برای سازنده بصری؟) **از قبل حل شده است.** نقش `CONTENT_EDITOR` هر دو `CONTENT_MANAGE` و `STOREFRONT_LAYOUT_MANAGE` و `MEDIA_MANAGE` را دارد.

🔍 **FACT.** ساینیتایزر HTML موجود (`apps/catalog/services/html_sanitizer.py`, ۱۴۲ خط) — allowlist دقیق تگ/attribute/CSS-property/URL-scheme (فقط `http/https/mailto/tel`؛ `javascript:`/`data:` رد می‌شوند). `apps/storefront_builder/section_registry.py` برای `rich_text`/`image_text` به همین ساینیتایزر و به `apps.content.models.validate_external_url` (که خودش `javascript:`/`data:`/`vbscript:` و URL نسبی-پروتکل را رد می‌کند) وصل است.

🔍 **FACT.** Rate limiting **از قبل به‌عنوان زیرساخت عمومی وجود دارد** (`apps/core/services/rate_limit.py`) — بر خلاف فرض ممیزی قبلی (که آن را غایب فرض کرده بود)، این سؤال باز شماره ۵ گزارش قبلی را حل می‌کند: بله، rate limiting باید (و از قبل با همین زیرساخت) اضافه شود.

🔍 **FACT.** Store همچنان مرز مستأجر است (بدون استثنا) — همه مدل‌های `storefront_builder` یا مستقیماً `store` FK دارند یا از طریق زنجیره FK (`version__layout__store`) تفکیک می‌شوند؛ `content` App هنوز به‌صورت «نرم» (nullable) روی مدل‌های صفحه اصلی (`ContentPage`, `HeroSlide`, `PromotionalBanner`, `SocialLink`, `Menu`) Store-scoped است — رکوردهای بدون Store (`store=NULL`) روی هیچ storefront نمایش داده نمی‌شوند اما در دیتابیس باقی می‌مانند (میگریشن ۰۰۱۵، `apps/content/migrations/0015_assign_legacy_content_ownership.py`).

---

## ۸. کش و کارایی

🔍 **FACT.** هنوز **هیچ لایه کشی روی رندر storefront وجود ندارد** — بدون تغییر نسبت به ممیزی 2026-08-03؛ `shop_core/settings.py` فاقد `CACHES` سفارشی است، `cache_page` در هیچ view واقعی استفاده نمی‌شود (تأیید مجدد با grep در کل کدبیس). تنها دو مصرف‌کننده موجود کش (`django.core.cache.cache`) کاملاً بی‌ربط‌اند: شمارنده‌های rate-limit و کش تک‌ردیفی `PlatformConfiguration`.

🔍 **FACT.** `Product.sold_count` (`apps/catalog/models.py:191`) هنوز **بدون هیچ writer** است — هیچ سیگنال/سرویسی در `apps/orders` آن را افزایش نمی‌دهد؛ خودِ `apps/dashboard/services/dashboard_service.py` هم این را می‌داند و به‌جایش مستقیماً از `OrderItem` واقعی محاسبه می‌کند (نه از فیلد استاتیک). بخش section `best_sellers` (`render_service.py`, `.order_by("-sold_count")`) روی داده‌ای می‌نشیند که به‌روز نمی‌شود.

---

## ۹. ماتریس خلاصه — الزامات کاربر در برابر وضعیت فعلی

| قابلیت درخواستی کاربر | وضعیت | مرجع |
|---|---|---|
| مدیر بدون کدنویسی چیدمان صفحه اصلی بسازد | ✅ EXISTS | بخش ۲ |
| Drag-and-drop + دکمه بالا/پایین موبایل | ✅ EXISTS | بخش ۲.۶ |
| فعال/غیرفعال/تکثیر/حذف section | ✅ EXISTS | بخش ۲.۵ |
| چند نمونه از یک نوع section | ✅ EXISTS | بخش ۲.۱ |
| Draft/Preview/Publish/Rollback صفحه اصلی+هدر+فوتر | ✅ EXISTS | بخش ۲.۳ |
| مهاجرت بدون‌خرابی فروشگاه موجود | ✅ EXISTS | بخش ۲.۷ |
| Collapse-in-editor مستقل از غیرفعال‌سازی storefront | ❌ ABSENT | بخش ۳ |
| Preview لینک/دستگاه واکنش‌گرا | ⚠️ PARTIAL (preview هست، سوییچ دستگاه/لینک قابل‌اشتراک نیست) | بخش ۳ |
| Undo/Redo، Autosave، Scheduled Publish | ❌ ABSENT | بخش ۳ |
| Section Registry واقعی با schema/data source | ⚠️ PARTIAL (Registry هست، schema/data-source نیست) | بخش ۲.۲ |
| تعویض کامل قالب بصری سایت (نه فقط تاکسونومی) | ❌ ABSENT | بخش ۴ |
| Template Definition جدا از Preset | ⚠️ PARTIAL (فقط برای صنف کاتالوگ، نه بصری) | بخش ۴ |
| Preset با فونت/spacing/radius/animation | ❌ ABSENT (فقط رنگ) | بخش ۵ |
| کالکشن مرچنت (Manual) | ⚠️ CONFLICTING (فقط Tag، نه Collection واقعی) | بخش ۶ |
| کالکشن هوشمند (Smart) | ❌ ABSENT | بخش ۶ |
| Data Source امن/توسعه‌پذیر برای section محصولی | ⚠️ PARTIAL | بخش ۲.۲ |
| Header Builder | ✅ EXISTS (به‌عنوان بخشی از همان Layout Version) | بخش ۲.۱، ۲.۵ |
| Footer Builder | ✅ EXISTS (همان بالا) | بخش ۲.۱، ۲.۵ |
| Custom Pages (فراتر از Home) | ❌ ABSENT (فقط `ContentPage` ساده، بدون section builder) | — |
| Renderer مشترک Gallery/Builder/Storefront | ⚠️ PARTIAL (بدنه مشترک، پوسته صفحه تکراری) | بخش ۲.۴ |
| Multi-tenancy کامل روی مدل‌های builder | ✅ EXISTS | بخش ۷ |
| مجوز اختصاصی builder | ✅ EXISTS (`STOREFRONT_LAYOUT_MANAGE`) | بخش ۷ |
| Rate limiting عملیات حساس | ✅ EXISTS | بخش ۷ |
| Responsive per-section (ستون/نمایش per-device) | ❌ ABSENT | بخش ۳ |
| کش storefront | ❌ ABSENT | بخش ۸ |
| نوشتن `sold_count` واقعی | ❌ ABSENT | بخش ۸ |

---

## ۱۰. ریسک‌های شناسایی‌شده

🔍 **FACT/💡 ترکیبی:**

1. **درز پوسته صفحه (بخش ۲.۴):** دو تمپلیت مستقل preview/storefront یعنی هر تغییر در منطق هدر/فوتر باید دوبار دستی اعمال شود؛ فراموشی یک‌طرف یعنی Preview دیگر نماینده واقعی storefront نیست — نقض مستقیم اصل غیرقابل‌مذاکره بخش ۱۲/۱۳ کار کاربر.
2. **`ProductTag(purpose="collection")` به‌عنوان یک راه‌حل نیم‌بند:** اگر تیم توسعه به اشتباه این را به‌جای یک مدل Collection واقعی گسترش دهد، آینده Smart Collection/SEO/تصویر مستقل کالکشن را قفل می‌کند چون `ProductTag` همچنان باید نقش «تگ جست‌وجوی معمولی» را هم ایفا کند.
3. **`sold_count` بدون writer:** section «پرفروش‌ترین‌ها» در سازنده بصری فعلاً روی داده‌ای غیرقابل‌اعتماد می‌نشیند — این نقص از پیش‌ازاین به ارث رسیده و اکنون در معرض کاربر نهایی (storefront عمومی) قرار دارد.
4. **بدون کش:** با افزودن section محصولی بیشتر (کالکشن، برند، چندنمونه‌ای)، تعداد کوئری per-request صفحه اصلی می‌تواند به‌سرعت رشد کند؛ نبود لایه کش یک ریسک کارایی واقعی برای فروشگاه‌های پرترافیک است.
5. **سند مرجع محصول قدیمی است:** `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` (بخش ۱۱.۸/۱۱.۹) صراحتاً Page Builder را «ناقص» و «غایب» توصیف می‌کند در حالی که اکنون کاملاً کار می‌کند — اگر عامل بعدی فقط این سند را بخواند (نه کد را)، تصمیم غلط می‌گیرد. این سند باید پس از این ممیزی به‌روزرسانی شود (خارج از scope همین کار، اما باید به‌عنوان بدهی مستند ثبت شود).

---

## پیوست: ماتریس واقعیت در برابر توصیه

طبق همان الزام شفافیت گزارش قبلی: این سند تقریباً به‌طور کامل **FACT** است (بخش‌های ۲ تا ۹)؛ توصیه‌های معماری و طراحی به سند خواهر (`STOREFRONT_TEMPLATE_AND_BUILDER_ARCHITECTURE_PLAN.md`) موکول شده‌اند؛ تصمیمات باز در همان سند (بخش «تصمیمات باز») جمع‌بندی می‌شوند.

**هیچ کدی در این کامیت تغییر نکرده است. این سند فقط یک گزارش است.**
