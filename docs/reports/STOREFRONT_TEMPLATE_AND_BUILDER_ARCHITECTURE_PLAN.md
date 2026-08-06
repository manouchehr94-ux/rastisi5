# سند معماری: سیستم قالب/پریست، تعویض قالب، کالکشن مرچنت و تکمیل سازنده بصری

**فاز:** طراحی معماری (Phase 1) — فقط طراحی، بدون پیاده‌سازی.

این سند بر پایه‌ی یافته‌های `docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md` نوشته شده — هر ادعای وضعیت فعلی که اینجا تکرار می‌شود، ارجاع دقیقش در همان سند است، نه اینجا. این سند خودش عمدتاً 💡 **RECOMMENDATION** و ❓ **OPEN DECISION** است.

> **پیش‌فرض معماری راهنما:** سازنده بصری صفحه اصلی (`apps/storefront_builder`) از قبل کار می‌کند و کامل نباید بازنویسی شود. هر پیشنهاد این سند باید روی آن **بنا** شود، نه به‌جای آن.

---

## ۱. Template در برابر Preset — تعریف رسمی برای RastiSi4

💡 **تعریف پیشنهادی (متفاوت و دقیق‌تر از "Template" فعلی `IndustryTemplate`):**

| | **Storefront Template** (جدید) | **Storefront Preset** (جدید) | **IndustryTemplate** (موجود) |
|---|---|---|---|
| دامنه | ساختار بصری: کدام section-family در دسترس است، معماری Header/Footer، خانواده کارت محصول | تنظیمات ظاهری روی یک Template: رنگ، فونت، border-radius، spacing، نوع Hero، انیمیشن مجاز | تاکسونومی: دسته‌بندی، ویژگی، schema |
| مالکیت | Platform-owned، نسخه‌بندی‌شده | Platform-owned، وابسته به یک Template یا مستقل | Platform-owned، نسخه‌بندی‌شده |
| تعداد per Store | یک Template فعال در هر زمان | یک Preset فعال روی آن Template | یک Installation در کل عمر Store |
| اثر روی داده تجاری | هیچ (فقط بصری) | هیچ (فقط بصری) | فقط تاکسونومی (Category/Attribute)، نه محصول/سفارش |
| تغییر توسط مرچنت | بله، هر زمان | بله، هر زمان، مستقل از تعویض Template | خیر (فعلاً یک‌بار در عمر Store) |

💡 **چرا این دو باید از `IndustryTemplate` جدا باشند، نه گسترش آن:** `IndustryTemplate` (`apps/catalog/models.py:1332-1406`) با قرارداد صریح `StoreIndustryInstallation.store = OneToOneField(..., CASCADE)` بسته شده — یعنی **یک نصب در کل عمر Store**. این قرارداد دقیقاً برعکس نیازِ Template بصری است (تعویض آزاد، هر زمان، بدون اثر روی داده). گسترش دادن `IndustryTemplate` برای این کار یعنی یا این قرارداد یک-بار-نصب را برای همه مصرف‌کننده‌ها می‌شکند (خطر رگرسیون برای دامنه صنف)، یا یک لایه استثنا داخل همان مدل اضافه می‌شود (پیچیدگی مفهومی). بنابراین یک مدل جدید و مستقل `StorefrontTemplateDefinition` توصیه می‌شود — با کپی الگو (نه کد) از `IndustryTemplate`: نسخه‌بندی immutable با `(slug, version)`، `readiness`، `content_fingerprint`.

💡 **تعداد Template پیشنهادی برای RastiSi4.** بر اساس تحلیل دو فایل مرجع UX ضمیمه‌شده (`e-commerce-template-selection-page.zip`) — که در عمل نشان می‌دهد ۱۰۰+ "قالب" نمایشی آن‌ها در واقع یک ترکیب ثابت از `headerType` × `heroType` × `cardType` × `bannerType` × ۴ رنگ است (`TemplateConfig` در آن نمونه، فیلدهای `headerType`, `heroType`, `cardType`, `bannerType` را جدا از `primaryColor`/`secondaryColor`/`accentColor` نگه می‌دارد) — پیشنهاد می‌شود:

- **۳ تا ۶ Template واقعی** (تفاوت ساختاری: مثلاً «فروشگاهی کلاسیک»، «ویترین مینیمال»، «فشرده/بازار» — هرکدام معماری Header/Footer/Grid متفاوت).
- **هر Template، ۶ تا ۱۲ Preset** (رنگ از `theme_presets.py` موجود گسترش‌یافته با فونت/radius/spacing).
- ❌ **صد قالب مستقل توصیه نمی‌شود** — نگهداری صد Template مستقل (صد بار تمپلیت Django، صد بار تست رندر) غیرقابل‌نگهداری است؛ ترکیب Template×Preset با ریاضیات ضرب دکارتی (۶ Template × ۱۰ Preset = ۶۰ ترکیب قابل‌مرور) همان تنوع بصری را با هزینه نگهداری خطی (نه صدتایی) می‌دهد. این دقیقاً همان الگویی است که Shopify/سایر پلتفرم‌های واقعی استفاده می‌کنند و همان الگویی است که مخزن ضمیمه‌شده مرجع UX عملاً (بدون اینکه بگوید) پیاده کرده.

❓ **OPEN DECISION.** تعداد دقیق Template اولیه (۳ یا ۶) و اینکه آیا Preset باید per-Template محدود باشد یا برخی Preset بین چند Template مشترک باشند، نیاز به تصمیم محصولی کاربر دارد. پیشنهاد این سند: شروع با **۳ Template** (کمترین هزینه QA برای MVP)، هرکدام ۴-۶ Preset گسترش‌یافته از ۶ پریست رنگی موجود.

---

## ۲. مدل داده — انتخاب بین گزینه‌های A/B/C

💡 برای چیدمان صفحه اصلی این تصمیم **از قبل گرفته شده و پیاده‌سازی شده**: گزینه C (هیبرید) — `StorefrontLayoutVersion` (سند نسخه‌بندی‌شده، حاوی `header_config`/`footer_config` JSON) + `StorefrontSection` (ردیف نرمال‌شده با `settings` JSONField). این تصمیم **درست بوده و نباید تغییر کند** — تحلیل زیر همان استدلال گزینه C را برای دو نیاز جدید (Template/Preset و Collection) تکرار می‌کند.

### ۲.۱ برای Template/Preset

| گزینه | توضیح | ارزیابی |
|---|---|---|
| A. سند JSON خالص | یک JSONField روی Store که کل تعریف Template را حمل کند | ❌ رد — بدون schema سطح DB، امکان کوئری "همه فروشگاه‌های از Template X استفاده می‌کنند" (برای گزارش/migration) از دست می‌رود؛ اعتبارسنجی نسخه‌ی سازگار سخت می‌شود |
| B. کاملاً نرمال‌شده | جدول جدا برای هر ویژگی Template (رنگ در یک جدول، فونت در جدول دیگر) | ❌ رد — بیش‌ازحد نرمال برای دامنه‌ای که واقعاً یک "بسته تنظیمات" است؛ دقیقاً همان دلیل رد گزینه B در طراحی چیدمان (`STOREFRONT_VISUAL_BUILDER_AUDIT.md` بخش ۱۰) اینجا هم صدق می‌کند |
| **C. هیبرید (پیشنهادی)** | `StorefrontTemplateDefinition` (platform-owned، نسخه‌بندی‌شده، `(slug, version)`) + `StorefrontPreset` (platform-owned، FK به یک یا چند Template سازگار، JSONField تنظیمات: رنگ/فونت/radius/spacing/animation) + `StoreTemplateInstallation` (store-owned، OneToOne یا FK به Store، اشاره‌گر به Template+Preset فعال، **قابل تغییر هر زمان** — بر خلاف `StoreIndustryInstallation`) | ✅ انتخاب — دقیقاً همان استدلال کارایی/توسعه‌پذیری/rollback گزینه C چیدمان |

💡 **طرح جدولی پیشنهادی (سطح مفهومی):**

```
StorefrontTemplateDefinition       (platform-owned، (slug, version) یکتا)
  - slug, version, name, description, readiness
  - section_family: JSONField (لیست section_keyهایی که این Template پشتیبانی می‌کند/توصیه می‌کند)
  - header_architecture: CharField (مثلاً "centered" | "megamenu" | "drawer")
  - footer_architecture: CharField
  - card_family: CharField (نوع کارت محصول پیش‌فرض)
  - compatible_preset_family: CharField (کدام دسته از Preset با این Template کار می‌کند)
  - content_fingerprint

StorefrontPreset                    (platform-owned)
  - slug (یکتا)، name، template_family (کدام Templateها را پشتیبانی می‌کند)
  - colors: JSONField (گسترش ۴ رنگ فعلی theme_presets.py)
  - font_family: CharField
  - border_radius_scale: CharField ("none"|"md"|"xl"|"full")
  - spacing_scale: CharField
  - animation_style: CharField

StoreTemplateInstallation           (store-owned، OneToOne با Store یا با StorefrontLayout)
  - store
  - active_template (FK به StorefrontTemplateDefinition)
  - active_preset (FK به StorefrontPreset)
  - installed_at, installed_by
  - previous_template/previous_preset (برای rollback سریع بدون رجوع به تاریخچه کامل)
```

❓ **OPEN DECISION.** آیا `StoreTemplateInstallation` باید روی خودِ `StorefrontLayout` موجود (OneToOne با Store) قرار گیرد یا مدل کاملاً جدا باشد؟ پیشنهاد این سند: مدل جدا (شفافیت مفهومی — Layout درباره "کدام sectionها" است، Template Installation درباره "کدام پوسته بصری" است)، اما با FK اختیاری متقابل برای کوئری راحت.

### ۲.۲ برای Collection

مشابه استدلال بالا: گزینه C.

```
MerchantCollection                  (store-owned)
  - store (FK)
  - name, slug (یکتا per store)
  - description
  - image
  - is_active
  - collection_type: CharField ("manual" | "smart" — نسخه اول فقط "manual" مقداردهی می‌شود، اما فیلد از روز اول برای گسترش‌پذیری وجود دارد)
  - seo_title, seo_description
  - display_on_homepage: Boolean (یا از طریق section reference)

MerchantCollectionItem              (store-owned، through model)
  - collection (FK → MerchantCollection)
  - product (FK → Product)
  - order: PositiveIntegerField (ترتیب دستی — دقیقاً همان چیزی که در ProductTag غایب بود)
  - UniqueConstraint(collection, product)
```

💡 چرا `through model` به‌جای M2M ساده (مثل `Product.tags`): چون کاربر صراحتاً «مرتب‌سازی دستی کالاها» را خواسته — این نیازمند فیلد `order` روی خودِ رابطه است، نه فقط روی مدل کالکشن.

---

## ۳. تصمیم اجرایی درباره Collection: Manual در برابر Smart

💡 **پیشنهاد نسخه اول: فقط Manual Collection.** دلایل:
1. تمام زیرساخت لازم (`MerchantCollectionItem` + reorder pattern موجود در `brand_service.py`/`product_image_service.py`) از قبل در پروژه الگو دارد — می‌تواند مستقیماً کپی شود.
2. Smart Collection نیازمند یک DSL شرط (دسته‌بندی/برند/قیمت/موجودی/تخفیف/ویژگی/برچسب/تاریخ/پرفروش) است که با وضعیت فعلی `Product.sold_count` (بدون writer — به AUDIT بخش ۸ مراجعه شود) و نبود `is_featured` روی محصول، برخی شرط‌ها (پرفروش بودن) از روز اول قابل‌اعتماد نخواهند بود.
3. کاربر صراحتاً پرسیده «برای نسخه اول کدام مدل باید ساخته شود» — Manual کمترین ریسک و سریع‌ترین راه به MVP قابل‌استفاده است.

❓ **OPEN DECISION.** آیا Smart Collection باید در همان فاز اول به‌عنوان فیلد آماده (`collection_type` + `smart_rules: JSONField` خالی) در مدل رزرو شود (برای جلوگیری از migration بعدی) یا کاملاً به فاز بعد موکول شود؟ پیشنهاد: رزرو فیلد `collection_type` از روز اول (هزینه صفر، migration رایگان)، اما پیاده‌سازی موتور Smart Rule کاملاً به فاز بعدی موکول شود.

---

## ۴. Data Source برای Sectionهای محصولی — گسترش Section Registry

💡 **وضعیت فعلی (AUDIT بخش ۲.۲):** هر context builder (`_newest_products_context`, `_best_sellers_context`, ...) یک تابع مستقل با منبع hard-coded است — بدون امکان انتخاب "این نمونه از `featured_products` باید از کالکشن X بیاید نه از منطق پیش‌فرض".

💡 **پیشنهاد گسترش (بدون شکستن API موجود):** یک کلید استاندارد `data_source` به `settings` هر section محصولی اضافه شود:

```python
{
  "data_source": "manual" | "collection" | "category" | "brand" | "discounted" | "newest" | "best_selling" | "most_viewed",
  "collection_id": <int, فقط اگر data_source=="collection">,
  "category_id": <int, ...>,
  "brand_id": <int, ...>,
  "product_ids": [<int>, ...],   # فقط اگر data_source=="manual"
  "item_limit": <int>,
  "ordering": "manual" | "-created_at" | "-sold_count" | ...,
  "show_price": bool, "show_discount": bool, "show_rating": bool, "show_add_to_cart": bool,
  "desktop_columns": int, "tablet_columns": int, "mobile_columns": int,
  "autoplay": bool, "loop": bool, "show_arrows": bool, "show_dots": bool,
}
```

**اعتبارسنجی امن (تکرار الگوی موجود `_validate_image_text_settings`/`section_registry.py:71-87`):** یک تابع `validate_settings` جدید برای هر section محصولی باید:
- `data_source` را در برابر یک enum بسته (نه رشته آزاد) چک کند.
- اگر `collection_id`/`category_id`/`brand_id`/`product_ids` ست شده، **مالکیت Store** را در سرویس (نه در `clean()`) چک کند — دقیقاً همان الگوی `_get_scoped_product` (`apps/dashboard/views.py:1590-1592`) و `_get_scoped_section` (`apps/storefront_builder/views.py:117-122`).
- `item_limit`/`desktop_columns` و مشابه را در بازه معقول (مثلاً ۱ تا ۵۰، ۱ تا ۶) clamp کند.

💡 **اجرای data source در `render_service.py`:** هر context builder به یک تابع سوییچ تبدیل می‌شود که بر اساس `settings.data_source` منبع را انتخاب می‌کند، اما تمام مسیرها همچنان از `storefront_visible_products`/`storefront_listing_products` (`apps/catalog/services/product_publish_service.py:47-62`) عبور می‌کنند — یعنی هیچ data source هرگز محصول غیرقابل‌نمایش/متعلق به Store دیگر را برنمی‌گرداند.

---

## ۵. چرخه‌ی حیات — Template Switching (سناریوی کامل بخش ۱۸ کار کاربر)

💡 **الگوریتم پیشنهادی، دقیقاً روی معماری Draft/Publish موجود (بدون سیستم جدید):**

```
۱. فروشگاه از Template A + Preset A1 استفاده می‌کند
   (StoreTemplateInstallation.active_template = A، active_preset = A1)
   (StorefrontLayout.published_version دارای section هایی با section_key های خانواده A)

۲. مدیر Template B را از گالری انتخاب می‌کند (بدون تأیید نهایی)
   → یک "Template Switch Preview" ساخته می‌شود:
     - محصولات/کالکشن‌ها/سفارش‌ها/مشتریان دست‌نخورده (این‌ها اصلاً به Template وصل نیستند)
     - یک StorefrontLayoutVersion جدید با source=TEMPLATE_SWITCH ساخته می‌شود
       (دقیقاً مثل الگوی موجود apply_industry_layout با source=INDUSTRY_TEMPLATE،
        layout_service.py:194-231)
     - این Draft هرگز published_version را دست نمی‌زند

۳. الگوریتم Section Mapping (تابع جدید map_sections_to_template(current_sections, target_template)):
   برای هر section موجود در نسخه فعلی:
     الف) اگر section_key عیناً در target_template.section_family موجود است
          → section با همان settings به Draft جدید کپی می‌شود (فقط section_key حفظ، بدون افت داده)
     ب) اگر یک معادل نزدیک تعریف‌شده دارد (نگاشت ثابت پایتونی،
        مثلاً "hero_banner" همیشه معادل "hero_banner" در همه Templateهاست چون این یک
        section عمومی رجیستری است، نه بخشی از خودِ Template)
          → مستقیم منتقل می‌شود (چون Registry سراسری پلتفرم است، نه per-Template؛
             به بخش ۶ زیر مراجعه شود چرا Section Registry باید مستقل از Template بماند)
     ج) اگر section هیچ معادلی ندارد (endpoint حذف‌شده از Registry، بسیار نادر)
          → به‌جای حذف silent، در گزارش "ناسازگاری" (بخش ۴ زیر) فهرست می‌شود؛
             در Draft با is_active=False نگه داشته می‌شود (هرگز داده حذف نمی‌شود)

۴. سیستم یک "خلاصه تغییرات" می‌سازد و به مدیر نشان می‌دهد:
   - Sectionهای منتقل‌شده (تعداد)
   - Sectionهای غیرفعال‌شده به‌دلیل ناسازگاری (اگر باشد)
   - رنگ/فونت/Header/Footer قدیم در برابر جدید (Diff بصری، نه فقط متنی)

۵. مدیر Preview کامل می‌بیند (از همان render_service.build_render_items موجود،
   با Template B اعمال‌شده روی Draft)

۶. مدیر یا Publish می‌کند یا Cancel:
   - Cancel → discard_draft(store) موجود (layout_service.py:113-122)؛
     StoreTemplateInstallation دست‌نخورده باقی می‌ماند (چون هنوز عوض نشده)
   - Publish → یک تراکنش اتمیک واحد:
     الف) StorefrontLayoutVersion جدید published می‌شود (همان publish() موجود)
     ب) StoreTemplateInstallation.active_template/active_preset به‌روزرسانی می‌شود
        + previous_template/previous_preset ذخیره می‌شود (برای rollback سریع)

۷. نسخه قبلی (هم Layout Version قدیمی و هم Template Installation قدیمی) قابل Restore باقی می‌ماند
   (از همان history/restore موجود storefront_builder/views.py، بدون تغییر)
```

### ۵.۱ چرا Section Registry نباید per-Template باشد

💡 **تصمیم معماری کلیدی.** اگر هر Template لیست section-type مستقل خودش را داشت (مثلاً Template A فقط `hero_banner_A` را می‌شناسد)، الگوریتم Mapping در بالا تبدیل به یک مسئله واقعی و پیچیده N×M می‌شد. به‌جایش: **Section Registry (`section_registry.py`) یک منبع حقیقت واحد و سراسری پلتفرم باقی می‌ماند** (همان‌طور که امروز هست)؛ هر `StorefrontTemplateDefinition` فقط یک **زیرمجموعه توصیه‌شده** از همان Registry سراسری را به‌عنوان `section_family` اعلام می‌کند (مثلاً "این Template معمولاً `hero_banner`+`category_grid`+... را پیشنهاد می‌دهد")، اما **تفاوت بصری واقعی section از طریق Preset (رنگ/فونت/radius) و از طریق `template_variant` اختیاری روی خودِ template (مثلاً `hero_banner` با ظاهر "slider" در برابر "split" بسته به Template فعال) اعمال می‌شود، نه از طریق section-type جدا.**

این یعنی الگوریتم Mapping تقریباً همیشه به حالت (الف) بالا می‌رسد (section عیناً منتقل می‌شود) — چون Registry سراسری است — و حالت (ج) عملاً فقط برای «section حذف‌شده از کل Registry» (نه به‌خاطر تعویض Template) اتفاق می‌افتد. این طراحی دقیقاً همان دلیلی است که Section Registry امروز هم پلتفرم‌محور و مستقل از `IndustryTemplate` طراحی شده — الگو تکرار می‌شود، نه شکسته.

❓ **OPEN DECISION.** آیا Templateهای مختلف باید ظاهر بصری متفاوت برای همان section_key ارائه دهند (مثلاً `hero_banner` در Template A به‌صورت اسلایدر و در Template B به‌صورت اسپلیت رندر شود)؟ اگر بله، این باید از طریق یک `template_variant` روی تمپلیت رندر section (نه section-type جدید) اعمال شود — پیشنهاد این سند تعریف یک فیلد اختیاری `render_variant` در `settings` هر section است که مقدار پیش‌فرضش از `StorefrontTemplateDefinition` فعال می‌آید.

---

## ۶. سازنده بصری — تکمیل شکاف‌های شناسایی‌شده در AUDIT

### ۶.۱ `collapsed_in_editor` مستقل از `enabled_on_storefront`

💡 یک فیلد UI-only ساده: `StorefrontSection.collapsed_in_editor` (BooleanField، پیش‌فرض False) — بدون اثر روی `render_service.build_render_items` (که فقط `is_active` را چک می‌کند). این فقط state ذخیره‌شده سرور است (نه session، چون کاربر ممکن است بین دستگاه‌ها/جلسات ادامه دهد) — یک migration کوچک و بدون‌ریسک روی مدل موجود.

### ۶.۲ Preview قابل‌اشتراک

❓ **OPEN DECISION (تکرار سؤال باز گزارش قبلی، هنوز حل‌نشده).** اگر preview فقط برای خودِ merchant است (وضعیت فعلی: session-based staff-only، مثل `product_preview`)، نیازی به توکن جدید نیست. اگر باید با افراد خارج پنل (مثلاً تیم طراحی) به‌اشتراک گذاشته شود، باید یک preview token امضاشده (الگوی `apps/portal/services/handoff_service.py` — تنها الگوی signed-token موجود در مخزن، با `TimestampSigner`) ساخته شود، منقضی‌شونده، فقط-خواندنی، و مقیّد به یک `StorefrontLayoutVersion` خاص (نه کل ادیتور). **پیشنهاد این سند: نسخه اول فقط session-based (مثل امروز)، توکن قابل‌اشتراک به فاز بعد موکول شود.**

### ۶.۳ Undo/Redo در برابر Autosave

❓ **OPEN DECISION.** با توجه به اینکه سیستم فعلی از قبل **بدون Autosave** (ذخیره صریح با دکمه) کار می‌کند و تست‌ها روی همین فرض نوشته شده‌اند، پیشنهاد این سند: **Save دستی حفظ شود** (نه Autosave) — چون Autosave با معماری «یک Draft واحد per Store» (`StorefrontLayout.draft_version`, یک OneToOne) به‌طور طبیعی سازگار است اما ریسک از‌دست‌رفتن تغییرات تصادفی (ذخیره خودکار یک اشتباه) را بالا می‌برد؛ به‌جایش، یک **هشدار «تغییرات ذخیره‌نشده» سمت کلاینت** (JS `beforeunload`) کافی و کم‌ریسک‌تر است. Undo/Redo گرانولار (نه در سطح کل Draft) پیچیدگی بالایی دارد (نیازمند یک event-log per-field) — پیشنهاد می‌شود **به فاز بسیار بعدی موکول شود**؛ در نسخه اول، «بازگردانی به نسخه منتشرشده قبلی» (که از قبل وجود دارد) جایگزین کافی Undo در سطح درشت است.

### ۶.۴ Scheduled Publish

💡 یک فیلد اختیاری `scheduled_publish_at` روی `StorefrontLayoutVersion` (Draft) + یک management command دوره‌ای (الگوی مشابه `expire_inventory_reservations` که از قبل در پروژه به‌عنوان یک الگوی cron-command امن وجود دارد) که هر Draft با `scheduled_publish_at <= now()` را از طریق همان تابع موجود `layout_service.publish()` منتشر می‌کند — **بدون منطق publish جدید، فقط trigger زمان‌بندی‌شده روی همان مسیر دستی.**

❓ **OPEN DECISION.** آیا این پروژه زیرساخت اجرای دوره‌ای (cron/Celery beat) دارد؟ طبق سند مرجع محصول (`00_PROJECT_MASTER_REFERENCE.md` بخش ۲۰، «Background Job») استفاده از Redis/Celery هنوز به‌صراحت خارج از Scope فازهای جاری اعلام شده. اگر این محدودیت پابرجاست، Scheduled Publish باید به یک management command dispatch‌شده توسط cron سیستم‌عامل (نه Celery) محدود شود — سازگار با محدودیت موجود پروژه.

### ۶.۵ Responsive per-section

💡 گسترش `settings` schema (نه یک مدل جدید) با یک زیرشیء استاندارد اختیاری:

```python
"responsive": {
  "hide_on_mobile": bool, "hide_on_tablet": bool, "hide_on_desktop": bool,
  "mobile_columns": int, "tablet_columns": int, "desktop_columns": int,
}
```

این با همان الگوی `_validate_image_text_settings` اعتبارسنجی می‌شود (مقادیر عددی clamp، بولین‌ها مستقیم). رندر HTML/CSS مربوطه (`storefront_builder/templates/storefront_builder/sections/*.html`) باید از این مقادیر برای `grid-template-columns` واکنش‌گرا و `class="hidden md:block"` مشابه استفاده کند — این بخش پیاده‌سازی UI است، نه تغییر معماری.

---

## ۷. Header/Footer — تأیید تصمیم موجود + قوانین ایمنی

💡 **تصمیم قبلاً گرفته‌شده و پیاده‌سازی‌شده (سؤال باز شماره ۱ گزارش قبلی، اکنون بسته): هدر/فوتر داخل همان `StorefrontLayoutVersion` هستند** (`header_config`/`footer_config` JSONField مستقیم روی همان مدل نسخه‌بندی‌شده صفحه اصلی — `models.py:122-123`). این سند این تصمیم را **تأیید** می‌کند و پیشنهاد بازنگری آن را ندارد — استدلال اصلی («هدر/فوتر در هر صفحه رندر می‌شوند، پس باید همان دقتِ Draft/Publish/Rollback را داشته باشند») هنوز معتبر است و کد فعلی (`HEADER_TOGGLE_FIELDS`/`FOOTER_TOGGLE_FIELDS`، `models.py:39-46`) دقیقاً این را پیاده کرده.

💡 **عناصر غیرقابل‌حذف (باید در سرویس اعمال شوند، نه فقط UI):** طبق توصیه گزارش قبلی (که هنوز اجرا نشده — نیاز به بررسی دقیق در `storefront_header_editor`/`storefront_footer_editor`، `views.py:309-347`):
- دسترسی به سبد خرید همیشه باید رندر شود (نمی‌توان `show_cart=False` و همزمان راه دیگری برای رسیدن به سبد نداشت).
- حداقل یک راه ورود به صفحه اصلی (لوگو یا لینک خانه) باید همیشه فعال بماند.
- فوتر باید حداقل یک ستون/بخش فعال داشته باشد.

❓ **OPEN DECISION — آیا این محدودیت‌ها اکنون در `layout_service`/`views.py` اعمال می‌شوند؟** طبق یافته‌های AUDIT (بخش ۲.۵)، تست `test_header_editor_saves_config` فقط تأیید می‌کند که toggle نشدن یک فیلد به `False` صحیح ذخیره می‌شود — **هیچ تستی برای «رد کردن یک ترکیب که سبد خرید و لوگو را همزمان مخفی می‌کند» یافت نشد.** این یک شکاف امنیتی/UX واقعی است (نه فرضی) که باید در فاز بعدی به‌عنوان یک اعتبارسنجی سرویس (`validate_header_config`/`validate_footer_config`) اضافه شود — قبل از توسعه بیشتر Header Builder.

---

## ۸. Renderer مشترک — رفع نقص پوسته صفحه

💡 **مشکل شناسایی‌شده در AUDIT بخش ۲.۴:** `preview.html` و `home_visual.html` پوسته صفحه (هدر/ناوبری/فوتر) را مستقل و دستی تکرار کرده‌اند.

💡 **راه‌حل پیشنهادی:** استخراج یک partial مشترک `apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html` و `.../page_shell_footer.html` که هر دو از `effective_header_config()`/`effective_footer_config()` (متدهای موجود روی خودِ `StorefrontLayoutVersion`، `models.py:149-156`) مستقیماً می‌خوانند. تفاوت‌های عمدی (لینک‌های غیرفعال در preview staff-only، مگامنو در storefront عمومی) باید از طریق یک پرچم `{% if is_live_storefront %}` داخل همان partial مشترک کنترل شوند، نه با دو فایل جدا. این یک تغییر **پرریسک کم اما اثر بالا** است — چون مستقیماً به اصل غیرقابل‌مذاکره کاربر («Preview باید دقیقاً همان storefront باشد») می‌رسد؛ باید زودتر از افزودن هر section جدید انجام شود، چون هر section جدید که به هر دو تمپلیت اضافه می‌شود، ریسک واگرایی را تشدید می‌کند.

💡 **جایگاه Renderer برای Template Gallery Preview (نیاز جدید این فاز):** پیش‌نمایش گالری Template (پیش از نصب/تعویض) باید از همان `render_service.build_render_items` استفاده کند، اما روی یک `StorefrontLayoutVersion` **موقت و ذخیره‌نشده در دیتابیس** (in-memory، ساخته‌شده از `StorefrontTemplateDefinition.section_family` پیش‌فرض + داده‌های نمونه یا داده واقعی همان Store اگر موجود باشد) اجرا شود. این یعنی تابع `build_render_items` باید بتواند یک شیء `StorefrontLayoutVersion` unsaved (نه لزوماً persisted) را بپذیرد — به بررسی دقیق امضای تابع در فاز پیاده‌سازی نیاز دارد (تغییر احتمالاً کوچک: تابع همین الان روی `version.sections` که یک related manager است تکیه می‌کند؛ برای نسخه in-memory باید یک مسیر جایگزین بپذیرد لیست section به‌جای query).

---

## ۹. مالکیت داده — Platform-owned در برابر Store-owned

💡 **جدول کامل برای مدل‌های جدید این فاز (تکرار الگوی جدول مشابه در `00_PROJECT_MASTER_REFERENCE.md` بخش ۸):**

| مدل | مالکیت | دلیل |
|---|---|---|
| `StorefrontTemplateDefinition` | Platform-owned | مثل `IndustryTemplate` — یک تعریف پلتفرمی، تمام فروشگاه‌ها می‌بینند |
| `StorefrontPreset` | Platform-owned | همان بالا |
| `StoreTemplateInstallation` | Store-owned (FK/OneToOne به Store) | اشاره‌گر مصرف هر Store به یک Template+Preset |
| `MerchantCollection` | Store-owned | مستقیماً درخواست کاربر |
| `MerchantCollectionItem` | Store-owned (از طریق `collection`) | همان بالا |
| `StorefrontLayout`/`Version`/`Section` | Store-owned (موجود) | بدون تغییر |
| `SECTION_REGISTRY` (رجیستری پایتونی) | Platform-owned (کد، نه دیتابیس) | بدون تغییر — طبق بخش ۵.۱ باید سراسری بماند |

هیچ مدل جدید نباید بدون FK صریح به Store (یا زنجیره FK که به Store ختم شود) نوشته شود — تکرار اصل تثبیت‌شده کدبیس (`00_PROJECT_MASTER_REFERENCE.md` بخش ۱۹.۱: «هر Query داده مرچنت باید Store-scoped باشد»).

---

## ۱۰. امنیت — تحلیل ریسک برای قابلیت‌های جدید

💡 **جدول ریسک/کاهش، فقط برای موارد جدید نسبت به AUDIT بخش ۷:**

| ریسک جدید | کاهش پیشنهادی |
|---|---|
| ارجاع cross-store به `MerchantCollection` درون `settings.collection_id` یک section | همان الگوی اعتبارسنجی سرویس موجود (`_get_scoped_product`) برای `_get_scoped_collection` تکرار شود — بخش ۴ |
| نصب/تعویض Template روی Store اشتباه (IDOR روی `template_id`/`preset_id`) | `StorefrontTemplateDefinition`/`StorefrontPreset` عمومی خوانده می‌شوند (platform-owned، بدون IDOR واقعی چون همه Storeها به همه Templateها دسترسی خواندن دارند)؛ ریسک واقعی فقط در نوشتن `StoreTemplateInstallation` است که باید permission موجود `STOREFRONT_LAYOUT_MANAGE` را دوباره استفاده کند (نه مجوز جدید) |
| Custom CSS/HTML per Template یا per Preset | **رد صریح در نسخه اول** — دقیقاً همان تصمیم AUDIT/گزارش قبلی («ممنوع در نسخه اول») تکرار می‌شود؛ فونت/رنگ/radius فقط از طریق enum بسته (نه رشته آزاد CSS) انتخاب می‌شوند |
| رزرو دستی محصولات کالکشن (`MerchantCollectionItem.order`) — race condition روی reorder | تکرار الگوی `reorder_brands`/`reorder_product_images` **با اضافه‌کردن صریح `@transaction.atomic`** (نکته دقتی که در AUDIT بخش ۲.۶ برجسته شد — الگوی موجود این را ندارد، نباید کورکورانه کپی شود) |
| Rate limit روی publish/switch Template | تکرار مستقیم `enforce_rate_limit` موجود (`apps/core/services/rate_limit.py`) — بدون زیرساخت جدید |
| نشت کالکشن Store دیگر در فرم انتخاب دستی محصول کالکشن (اتوکامپلیت/جستجو) | فیلتر `store=` اجباری در هر endpoint جستجوی محصول برای افزودن به کالکشن — تست cross-store rejection مثل الگوی `test_views.py` موجود در storefront_builder |

💡 **جمع‌بندی سیاست HTML/JS آزاد:** طبق تحلیل کاربر (بخش ۱۵ کار او) و رویه موجود پروژه (`html_sanitizer.py` allowlist سختگیرانه)، این سند **هیچ فیلد `custom_html`/`custom_css`/`custom_js` جدیدی پیشنهاد نمی‌دهد** — نه در Template، نه در Preset، نه در Collection، نه در هیچ Section جدید. تنها مسیر محتوای غنی همان `rich_text`/`image_text` موجود با ساینیتایزر موجود باقی می‌ماند.

---

## ۱۱. کارایی و کش

💡 با توجه به AUDIT بخش ۸ (کش کاملاً غایب) و افزایش تعداد section محصولی محتمل (کالکشن + برند + چندنمونه‌ای)، این سند یک لایه کش حداقلی برای فاز پیاده‌سازی توصیه می‌کند (جزئیات کامل در سند نقشه‌راه):

- کش published layout render (نه Draft) با کلید `f"storefront:home:{store_id}:{published_version.content_fingerprint}"` — استفاده از `content_fingerprint` موجود (`models.py:158-170`) به‌جای timestamp یعنی invalidation خودکار با هر تغییر محتوایی، بدون نیاز به `cache.delete` صریح در همه جای کد.
- Preview/Draft همیشه کش را دور می‌زند (بدون تغییر نسبت به توصیه قبلی).
- کش نتایج هر Data Source (کالکشن/دسته/برند) جدا و کوتاه‌مدت (TTL چند دقیقه‌ای) — چون این‌ها ممکن است بین چند صفحه (Home، Collection Page مستقل) استفاده مجدد شوند.
- ❓ **OPEN DECISION.** پروژه فعلاً بدون `CACHES` سفارشی (فقط `LocMemCache` ضمنی Django) کار می‌کند. آیا معرفی یک backend کش مشترک (Redis) برای این فاز مجاز است، یا باید با همان `LocMemCache` پیش‌فرض (per-process، غیرمشترک بین workerها) کار کرد؟ طبق سند مرجع محصول، Redis هنوز به‌صراحت خارج از Scope فازهای جاری غیرمرتبط اعلام شده — این تصمیم باید صریحاً از کاربر گرفته شود پیش از افزودن کش واقعی.

---

## ۱۲. استراتژی Responsive — جمع‌بندی

💡 طبق بخش ۶.۵، تنظیمات Responsive که باید قابل‌تغییر باشند محدود به: `columns` (per-device)، `visibility` (hide on device)، و به‌صورت اختیاری `text_size`/`alignment` برای section‌های متنی (`rich_text`/`image_text`). **پیشنهاد می‌شود `spacing`/`image_ratio`/`stacking order` به فاز بعدی موکول شوند** — این‌ها نیازمند یک زبان طراحی کامل‌تر (Design Token) هستند که هنوز در `ShopSettings`/`theme_presets.py` وجود ندارد (بدون فیلد spacing/radius امروز). آزادی Responsive باید به همین چند کلید محدود بماند تا UI صفحه (به‌ویژه در Breakpoint 390px که کاربر صریحاً خواسته) با ترکیب‌های دلخواه مدیر خراب نشود.

---

## ۱۳. Custom Pages — دامنه پیشنهادی نسخه اول

💡 **پیشنهاد Scope:** Builder فقط برای Home Page در نسخه اول باقی بماند (بدون تغییر نسبت به وضعیت فعلی). دلیل: `ContentPage` موجود (`apps/content/models.py`) از قبل یک راه‌حل ساده برای صفحات ثابت (درباره ما، تماس) دارد؛ گسترش Section Builder به صفحات دلخواه نیازمند یک لایه routing جدید (کدام URL کدام Layout Version را رندر کند) است که خارج از scope همین فاز است. **معماری پیشنهادی (`StorefrontLayoutVersion` + `StorefrontSection`) طوری طراحی شده که در آینده به‌راحتی به چند Layout per Store گسترش یابد** (فقط باید `StorefrontLayout.store` از `OneToOneField` به `ForeignKey` + یک فیلد `page_type`/`slug` تغییر کند) — اما این تغییر مدل باید در فاز جدا و پس از تثبیت Home Page Builder انجام شود، نه همزمان.

---

## ۱۴. سؤالات باز — جمع‌بندی کامل

1. تعداد دقیق Template اولیه (۳ یا ۶) و ساختار دقیق `section_family` هر Template؟ (بخش ۱)
2. آیا `StoreTemplateInstallation` روی `StorefrontLayout` باشد یا مدل جدا؟ (بخش ۲.۱)
3. آیا `collection_type`/`smart_rules` باید از روز اول رزرو شوند؟ (بخش ۳)
4. آیا Templateهای مختلف باید ظاهر متفاوت برای همان section ارائه دهند (`render_variant`)؟ (بخش ۵.۱)
5. آیا Preview باید قابل‌اشتراک با افراد خارج پنل باشد (نیاز به توکن) یا session-based کافی است؟ (بخش ۶.۲)
6. Autosave یا Save دستی؟ (پیشنهاد این سند: دستی — بخش ۶.۳)
7. آیا Scheduled Publish در نسخه اول لازم است، با توجه به محدودیت عدم‌وجود Celery؟ (بخش ۶.۴)
8. آیا معرفی Redis/کش مشترک برای این فاز مجاز است؟ (بخش ۱۱)
9. آیا Custom CSS مجاز باشد (حتی محدود، مثلاً فقط چند متغیر عددی)؟ پیشنهاد این سند: خیر در نسخه اول. (بخش ۱۰)
10. آیا Custom HTML مجاز باشد؟ پیشنهاد این سند: خیر، هرگز (فقط `rich_text` با ساینیتایزر موجود). (بخش ۱۰)
11. سطح آزادی تنظیمات Section — آیا مدیر باید بتواند مستقیماً CSS override تزریق کند؟ پیشنهاد: خیر؛ فقط از طریق enumهای بسته (رنگ/فونت/radius از Preset). (بخش ۱۲)
12. Storefront cache چگونه invalidate شود — با `content_fingerprint` موجود (پیشنهاد این سند) یا مکانیزم زمان‌محور (TTL ساده)؟ (بخش ۱۱)

---

## پیوست: توصیه MVP نسخه اول (خلاصه تصمیم‌گیری)

💡 برای جلوگیری از دامنه بیش‌ازحد بزرگ، این سند برای فاز پیاده‌سازی بلافاصله بعدی این حداقل را پیشنهاد می‌دهد (جزئیات فازبندی کامل در `STOREFRONT_TEMPLATE_AND_BUILDER_IMPLEMENTATION_ROADMAP.md`):

- ✅ `MerchantCollection` + `MerchantCollectionItem` (فقط Manual) + reorder دستی + مجوز موجود
- ✅ گسترش `data_source` روی Sectionهای محصولی موجود (بدون section-type جدید) تا شامل «کالکشن» شود
- ✅ رفع نقص پوسته صفحه تکراری (`preview.html`/`home_visual.html`)
- ✅ `collapsed_in_editor` (فیلد ساده)
- ✅ اعتبارسنجی سرویس برای عناصر غیرقابل‌حذف Header/Footer
- ⏸ Template Definition/Preset کامل (پیچیدگی بالاتر، فاز جدا)
- ⏸ Smart Collection، Undo/Redo، Scheduled Publish، Custom Pages، کش Redis (فازهای بعدی)

**هیچ کدی در این کامیت تغییر نکرده است. این سند فقط طراحی است.**
