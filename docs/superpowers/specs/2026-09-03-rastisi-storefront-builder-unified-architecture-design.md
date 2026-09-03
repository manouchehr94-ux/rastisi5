# RastiSi R4 — Unified Storefront Builder, Store Appearance Engine & 50 Ready Templates Architecture

**نسخه:** 2.0 — Unified Architecture
**تاریخ:** 2026-09-03
**وضعیت:** سند معماری یکپارچه برای بازبینی مالک محصول؛ مبنای برنامه‌ریزی اجرایی پس از تأیید
**دامنه:** Storefront Builder، Store Appearance / Design Engine، Direct Preview Editing، Content Hub، Design Lab، 50 Ready Templates، Demo Store، Product Detail presentation، Campaign/Timed-offer presentation، Versioning، Security و QA

---

## 1. تعریف یک‌جمله‌ای محصول

> **راستی‌سی یک موتور مرکزی و مشترک برای ظاهر فروشگاه دارد که از اجزای بصری ثبت‌شده، نسخه‌دار، امن و قابل‌ترکیب ساخته شده است؛ 50 قالب آماده‌ی رسمی فقط DNAهای حرفه‌ای و تست‌شده‌ای روی همین موتور هستند، و صاحب فروشگاه باید بتواند عمدتاً با دیدن فروشگاه، کلیک‌کردن روی همان چیزی که می‌خواهد، تغییر دادن آن و مشاهده‌ی نتیجه به‌صورت زنده، فروشگاهش را بسازد و نگهداری کند.**

اصل محصول در یک عبارت:

> **قدرت در معماری، سادگی در رابط کاربری.**

و تجربه‌ی مطلوب صاحب فروشگاه:

> **ببین، کلیک کن، تغییر بده، همان لحظه نتیجه را ببین، و وقتی آماده بودی منتشر کن.**

---

# بخش اول — جایگاه این سند و قواعد حاکم

## 2. رابطه با معماری موجود R4

این سند جایگزین اصول پایه‌ی R4 نمی‌شود؛ آن‌ها را یکپارچه و دقیق‌تر می‌کند.

تمام invariantهای زیر همچنان قطعی‌اند:

- یک Builder shell؛
- یک قرارداد مشترک برای mutationهای Draft؛
- یک Preview/Public rendering engine مشترک؛
- Public فقط از مسیر Publish تغییر می‌کند؛
- stale write باید رد شود؛
- هیچ HTML/CSS/JavaScript دلخواه Merchant وارد renderer نمی‌شود؛
- هیچ raw JSON اجرایی، template path دلخواه یا renderer name دلخواه پذیرفته نمی‌شود؛
- Responsive رفتار خود Componentها و Design System است، نه یک Mobile Builder دوم؛
- Global Design پایه است و local overrideها sparse و typed هستند؛
- Templateها codebase مستقل، Builder مستقل یا renderer مستقل ندارند؛
- Appearance و Content روی همان domain contracts و renderer واقعی Public کار می‌کنند.

این سند دو لایه‌ای را که تا امروز جدا توضیح داده شده بودند به یک مدل واحد تبدیل می‌کند:

1. **لایه‌ی موتور و قراردادهای مهندسی:** Store Appearance Engine، registries، component identities، 50 recipes، Design Lab، security، versioning، QA.
2. **لایه‌ی تجربه‌ی صاحب فروشگاه:** Direct Editing، Content Hub، Parent/Child tabs، Live Preview، Media Picker، template-preserving content، ساده‌سازی Header/Footer/Mega Menu و صفحه محصول.

هیچ‌کدام نباید برای پیاده‌سازی دیگری دور زده شوند.

---

## 3. قاعده‌ی رفع تعارض میان تصمیم‌ها

اگر دو requirement ظاهراً با هم تعارض داشتند، این ترتیب ملاک است:

1. **حقیقت تجاری و امنیت** هرگز توسط آزادی طراحی نقض نمی‌شود.
2. **یک موتور/یک renderer/یک Draft lifecycle** هرگز برای راحتی کوتاه‌مدت شکسته نمی‌شود.
3. **سادگی UX کاربر عادی** بر نمایش مستقیم پیچیدگی موتور اولویت دارد.
4. **Template DNA پیش‌فرض است، نه قفل دائمی.**
5. **Override محلی مجاز است، اما فقط در محدوده‌ای که آن Component به‌صورت typed و امن پشتیبانی می‌کند.**
6. Header/Footer/Mega Menu عمداً Componentهای محافظت‌شده‌تری هستند و نسبت به Home sectionهای عادی آزادی کمتری دارند.
7. Design Lab می‌تواند combinatorial power بیشتری را نشان دهد، اما همچنان فقط همان componentهای ثبت‌شده و همان shared renderer را استفاده می‌کند.

---

# بخش دوم — مدل کلان محصول

## 4. یک موتور، پنجاه قالب، محتوای مستقل

راستی‌سی 50 فروشگاه مستقل نمی‌سازد.

مدل صحیح:

```text
Store Content / Commerce Truth
            +
Store Appearance Component Library
            |
            v
      Shared Renderer
            |
            +--------------------+
            |                    |
      Ready Templates        Direct Editing
       (50 DNAs)             / Content Hub
            |                    |
            +---------+----------+
                      v
                 Merchant Draft
                      |
                   Publish
                      |
                 Public Store
```

50 Ready Template فقط 50 recipe حرفه‌ای و curated روی یک engine مشترک هستند.

بنابراین:

- Template محتوای فروشگاه نیست.
- Template محصول، قیمت، موجودی، دسته‌بندی واقعی یا برند واقعی تولید نمی‌کند.
- Template انتخاب می‌کند محتوا چگونه نمایش داده شود.
- Merchant می‌تواند پس از انتخاب Template، بخش‌های مجاز را independently تغییر دهد.
- همه‌ی Templateها از renderer مشترک Public استفاده می‌کنند.

اصل:

> **Curated by RastiSi, customizable by the merchant.**

---

## 5. جدایی چهار مفهوم اصلی

برای جلوگیری از پیچیدگی و coupling باید چهار مفهوم همیشه از هم متمایز بمانند:

### 5.1. Commerce / Catalog Truth

منبع حقیقت برای:

- Product
- Price
- Sale Price
- Stock
- SKU
- Variant
- Order
- Campaign rule
- Timed-offer validity
- Product imagery به‌عنوان asset اصلی کاتالوگ

### 5.2. Store Content

محتوای نمایشی و قابل مدیریت فروشگاه، مانند:

- Hero slides
- banners
- collection titles
- selected products for a section
- category presentation assets
- brand presentation assets
- stories
- blog/magazine content
- newsletter/trust/contact presentation
- store identity assets

### 5.3. Store Appearance

DNA و presentation، مانند:

- Header
- Mega Menu presentation
- Hero variant
- Layout
- Product View
- Product Card
- Button/Badge/Tag/Ribbon language
- Motion
- Footer
- Bottom Navigation
- Palette
- Typography
- Radius
- Density
- Width
- Shadow
- Spacing

### 5.4. Builder Experience

رابطی که Store Content و Store Appearance را بدون لو دادن پیچیدگی فنی مدیریت می‌کند:

- Direct Preview Editing
- Parent/Child context
- tabs
- Live Preview
- Autosave
- Content Hub
- Media Picker
- Undo/Redo/History
- Publish

این چهار بخش ممکن است در UI کنار هم دیده شوند، اما source of truth آن‌ها نباید مخلوط شود.

---

# بخش سوم — Store Appearance Engine

## 6. مرز منطقی Store Appearance

کد باید یک مرز منطقی روشن به نام Store Appearance داشته باشد؛ نام package نهایی می‌تواند با conventions موجود repo هماهنگ شود.

Conceptual shape:

```text
storefront_appearance/
  contracts
  component-family definitions
  registry/resolution adapters
  compatibility metadata
  template recipes
  preview-manifest validation
  version/deprecation rules
```

این مرز مجوز big-bang rewrite نیست.

ساختارهای موجود R4 مانند موارد زیر باید reuse/evolve شوند:

- `appearance_registry.py`
- `global_region_registry.py`
- `section_registry.py`
- `layout_preset_registry.py`
- Variant contracts
- shared renderer
- versioned Draft/Published layout architecture

هیچ registry موازی فقط برای سیستم جدید ساخته نمی‌شود.

---

## 7. هویت پایدار Componentها

هر Component production یک key پایدار، allowlisted و قابل نسخه‌بندی دارد.

مثال:

```text
header.editorial_centered
mega_menu.visual_columns
hero.split_story
layout.editorial_spacious
product_view.featured_grid
card.portrait_minimal
badge.discount_corner
motion.soft_reveal
footer.magazine
bottom_nav.floating_pill
```

در UI می‌توان نام‌هایی مثل «هدر 08» یا thumbnail بصری نشان داد، اما persistence نباید به شماره‌ی نمایشی وابسته باشد.

Material redesign باید key/version جدید بگیرد، مثلاً:

```text
card.portrait.v1
card.portrait.v2
```

Merchant فقط reference به Component ثبت‌شده ذخیره می‌کند، نه HTML/CSS/JS Component.

---

## 8. خانواده‌های Component و اهداف کتابخانه

هدف معماری این است که library بزرگ و قابل‌گسترش باشد. اهداف اولیه‌ی طراحی عبارت بودند از:

| Component family | هدف اولیه‌ی محصول |
| --- | ---: |
| Header | 20 |
| Mega Menu presentation | 20 |
| Footer | 20 |
| Layout / composition | 20 |
| Hero / first slider | 20 |
| Product display / collection presentation | 15 |
| Product card | 30 |
| Motion profile | 20 |
| Discount / badge / promotional treatment | 15 |
| Mobile bottom navigation | 15 |
| Timed-offer / countdown | domain capability + curated presentations |

این اعداد **هدف اولیه‌ی library** هستند، نه دستور به بازسازی چیزهایی که قبلاً در repo ساخته شده‌اند. inventory واقعی registries منبع حقیقت implementation است و اجزای موجود باید reuse شوند.

افزودن خانواده‌های آینده مانند Announcement Bar، Sticky Buy Bar، Floating Cart، Comparison Drawer، Video Commerce یا 3D Viewer باید از همان contracts و safe-default rules پیروی کند.

---

## 9. Merchant Store Appearance State

Draft فروشگاه به‌صورت مفهومی انتخاب‌های typed زیر را نگه می‌دارد:

```text
header        = header.editorial_centered
mega_menu     = mega_menu.visual_columns
hero          = hero.split_story
layout        = layout.editorial_spacious
product_view  = product_view.featured_grid
card          = card.portrait_minimal
badge         = badge.discount_corner
motion        = motion.soft_reveal
footer        = footer.magazine
bottom_nav    = bottom_nav.floating_pill
palette       = <existing R4 palette key>
typography    = <existing R4 typography key>
```

storage دقیق باید از Draft/Published architecture موجود استفاده کند.

این initiative نباید appearance lifecycle جدیدی موازی با Draft موجود بسازد.

---

## 10. قانون mutation مستقل

تغییر یک Component فقط همان Component را عوض می‌کند، مگر اینکه Merchant صریحاً یک whole-template/preset operation انجام دهد.

مثال:

```text
before: header = header.editorial_centered
change: header = header.compact_search
```

نتیجه:

- Footer تغییر نمی‌کند.
- Card تغییر نمی‌کند.
- Palette تغییر نمی‌کند.
- Hero تغییر نمی‌کند.
- Bottom Nav تغییر نمی‌کند.

این یک hard product rule است.

---

# بخش چهارم — Ready Template DNA و 50 قالب رسمی

## 11. Ready Template چیست؟

هر Ready Template یک recipe نسخه‌دار از Componentهای سازگار و typed settings محدود است.

Conceptual example:

```text
Template 10
  schema_version = 1
  header         = header_08
  mega_menu      = mega_menu_03
  hero           = hero_14
  layout         = layout_07
  product_view   = product_view_11
  card           = card_15
  badge          = badge_05
  motion         = motion_03
  footer         = footer_12
  bottom_nav     = bottom_nav_09
  palette        = palette_18
  typography     = typography_x
  section_recipe = [...]
```

DNA می‌تواند typed overrides داشته باشد، اما هرگز شامل موارد زیر نیست:

- arbitrary HTML
- arbitrary CSS
- JavaScript
- executable expressions
- unrestricted JSON
- arbitrary template paths
- arbitrary renderer names

---

## 12. Template نقطه شروع است، نه محدودیت

Template باید defaults حرفه‌ای فراهم کند، از جمله:

- Palette
- Typography
- Background
- Border/Radius
- Shadow
- Spacing
- Layout
- Hero style
- Product Card style
- Button/Badge/Tag/Ribbon family
- Header
- Footer
- Mega Menu presentation
- Motion
- Bottom Navigation

اما Merchant پس از انتخاب Template، در محدوده‌ی capabilities ثبت‌شده‌ی Component می‌تواند local override داشته باشد.

هر override باید امکان روشن و ساده‌ی زیر را داشته باشد:

> **بازگشت به تنظیم قالب / استفاده دوباره از والد**

---

## 13. تغییر Template و حفظ محتوای Merchant

این بخش رفتار دقیق switching را قفل می‌کند.

### 13.1. در فروشگاه تازه یا Apply اولیه

اگر Merchant یک Template را برای اولین بار روی storefront اولیه اعمال می‌کند، Template می‌تواند recipe پیشنهادی section composition را نیز به Draft بدهد.

### 13.2. پس از اینکه Merchant فروشگاه را شخصی‌سازی کرده است

انتخاب Template جدید به‌طور پیش‌فرض باید:

- Design DNA را تغییر دهد؛
- merchant content را حفظ کند؛
- selected products/collections را حفظ کند؛
- uploaded assets را حفظ کند؛
- merchant texts را حفظ کند؛
- customized section structure را حفظ کند؛
- commerce/catalog data را هرگز تغییر ندهد.

اگر Merchant بخواهد composition پیشنهادی Template هم دوباره اعمال شود، باید یک action صریح و جدا مانند:

> **بازنشانی ساختار/محتوای نمایشی به پیشنهاد قالب**

انتخاب کند.

این action نیز نباید Demo product/catalog data را به Merchant copy کند.

---

## 14. تمام 50 قالب برای تمام صنایع

Industry فقط recommendation/ranking را تغییر می‌دهد.

هیچ industry نباید Template معتبر را مخفی یا ممنوع کند.

همیشه باید مسیر «نمایش همه 50 قالب» وجود داشته باشد.

---

## 15. Template Demo در برابر Template Preset

این دو مفهوم باید جدا بمانند:

### Template Demo

Template واقعی روی canonical Demo Store رندر می‌شود تا کاربر پتانسیل آن را ببیند.

### Template Preset

فقط design/layout DNA روی Merchant Draft اعمال می‌شود.

Template selection هرگز Demo catalog/business data را به Merchant منتقل نمی‌کند.

---

# بخش پنجم — تجربه‌ی اصلی Builder

## 16. Builder عادی باید ساده‌تر از Engine باشد

Merchant نباید برای تغییر Hero یا Header نیاز داشته باشد بفهمد:

- registry چیست؛
- schema_version چیست؛
- renderer چه مسیری دارد؛
- `section=None` یعنی چه؛
- model relation یا fallback چگونه کار می‌کند؛
- breakpoint چیست؛
- component key چیست.

این‌ها concern مهندسی‌اند.

Normal Builder باید فقط قابلیت‌های مرتبط با context جاری را نشان دهد.

---

## 17. دو مسیر مکمل: Direct Editing + Content Hub

دو surface وجود دارد، اما هر دو روی **همان data و همان contracts** کار می‌کنند.

### 17.1. Direct Preview Editing — مسیر اصلی

اصل:

> **What you see is what you edit.**

Merchant روی همان چیزی که در Preview می‌بیند کلیک می‌کند.

نمونه:

- text → text settings
- Hero → Hero settings
- logo → logo settings
- banner → banner settings
- collection section → collection/content/display settings
- brands → brand selection/order/display
- badge → badge settings
- product card → card presentation settings + product-management shortcut where relevant

### 17.2. Content Hub — مسیر مرکزی و bulk

برای کارهایی که از یک view مرکزی بهتر انجام می‌شوند:

- store identity
- logo/media
- Hero assets
- banners
- category presentation assets
- brands
- collections
- stories
- blog/magazine
- newsletter/trust/contact content
- bulk media reuse

Content Hub سیستم دوم نیست؛ همان data را از نمای مدیریتی متفاوت نشان می‌دهد.

اگر یک entity مانند Product، Category یا Brand منبع حقیقت Catalog دارد، Content Hub فقط presentation/content مجاز را ویرایش می‌کند یا shortcut روشن به مدیریت source-of-truth می‌دهد؛ نباید ownership دامنه را به‌صورت پنهانی جابه‌جا کند.

### 17.3. Editor باید چیزی را که Renderer واقعاً نشان می‌دهد بفهمد

اگر Preview به دلیل inheritance، global region یا fallback معتبر محتوایی را نمایش می‌دهد، Direct Editor نباید به Merchant پیام متناقضی مثل «هیچ موردی وجود ندارد» نشان دهد.

سیستم باید provenance محتوای رندرشده را به context ویرایش نگاشت کند و آن را با زبان ساده نمایش دهد؛ برای مثال:

- «در حال استفاده از تنظیم سراسری»
- «در حال استفاده از تنظیم قالب»
- «برای این بخش اختصاصی کن»

Merchant نباید مفاهیمی مانند `section=None`، foreign key fallback یا global-source implementation را ببیند.

قاعده:

> **هر چیزی که در Preview دیده می‌شود باید یک مسیر ویرایش قابل‌فهم و منطبق با همان منبع واقعی داشته باشد.**

---

## 18. پنل ویرایش حدود 65–70 درصد

با کلیک روی عنصر در Preview، یک پنل بزرگ context-aware در desktop باز می‌شود که حدود 65 تا 70 درصد فضا را در اختیار settings می‌گذارد و Preview همچنان قابل مشاهده می‌ماند.

در Builder روی viewport کوچک، پنل می‌تواند fullscreen شود.

هدف:

- context حفظ شود؛
- Preview همیشه مقابل کاربر باشد؛
- navigation بین صفحه‌های متعدد حذف شود؛
- تنظیمات complex در فضای کافی ارائه شوند.

این «modal برای همه‌چیز» نیست؛ یک editor surface context-aware است.

---

## 19. Parent و Child هم‌زمان در دسترس

اگر Merchant روی یک child کلیک کند، child انتخاب اصلی است ولی parent باید همان‌جا قابل دسترسی باشد.

مثال:

```text
خانه ← پیشنهاد ویژه ← عنوان
```

Merchant می‌تواند بدون بستن editor به parent section برود.

---

## 20. ساختار تب‌دار Editor

بر اساس نوع عنصر، tabهای مرتبط نمایش داده می‌شوند.

Baseline:

- **محتوا**
- **ظاهر**
- **چیدمان**
- **افکت**
- **والد**
- **تنظیمات بیشتر**
- **بازگشت به قالب/والد**

همه‌ی tabها برای همه‌ی عناصر نمایش داده نمی‌شوند.

اصل:

> فقط settingsی نشان داده شوند که برای element انتخاب‌شده معنی دارند.

مثلاً icon نباید settings کل Hero را در tab اولیه نشان دهد؛ ولی parent از breadcrumb/tab قابل دسترس است.

---

## 21. Live Preview، Autosave Draft و Publish

هر تغییر معتبر باید به‌صورت فوری در Preview دیده شود:

- رنگ
- فونت
- متن
- عکس
- spacing
- layout/style
- badge style
- section order

هیچ Apply button روزمره برای این تغییرها لازم نیست.

flow:

```text
Edit
  -> validate typed mutation
  -> Draft autosave
  -> live Preview
  -> explicit Publish
  -> Public Store
```

Public هیچ‌گاه با autosave Draft تغییر نمی‌کند.

---

## 22. History و امنیت روانی کاربر

Merchant باید بتواند بدون ترس آزمایش کند.

Builder باید پشتیبانی کند:

- Undo
- Redo
- Revert to last Published
- Version history
- Restore previous version

Design Lab experiments تا زمان Apply نباید Draft history را با هر کلیک پر کنند؛ این موضوع در بخش Design Lab تعریف شده است.

---

# بخش ششم — Inheritance و Override

## 23. مدل ارث‌بری

ترتیب مفهومی:

```text
Template DNA
    ↓
Global Design System
    ↓
Page / Section Settings
    ↓
Element Settings
    ↓
Local Override
```

هر layer فقط زمانی layer بالاتر را override می‌کند که value typed و صریح داشته باشد.

در غیر این صورت از parent/default ارث می‌برد.

---

## 24. Override فرزند با تغییر والد حفظ می‌شود

مثال:

```text
Hero
├── Title       -> manual white color
├── Description -> inherits from Hero
└── CTA          -> inherits from Hero
```

اگر style والد Hero تغییر کند:

- Title که override دارد حفظ می‌شود.
- Description و CTA که inherit می‌کنند تغییر جدید والد را می‌گیرند.

برای هر override باید کنترل واضحی وجود داشته باشد:

> **استفاده دوباره از تنظیم والد / قالب**

تغییر parent نباید silently child overrides را پاک کند.

---

## 25. Override محلی محدود به capability واقعی Component است

«هر عنصر قابل ویرایش است» به معنی «هر property دلخواه CSS آزاد است» نیست.

هر Component schema تعریف می‌کند چه چیزهایی قابل تغییرند.

مثلاً یک Hero می‌تواند اجازه دهد:

- typography token
- color token
- alignment
- image
- CTA style
- spacing preset
- motion preset

اما Header محافظت‌شده ممکن است فقط اجازه دهد:

- logo
- background/text color token
- supported feature toggles
- sticky if supported

این distinction برای حفظ کیفیت طراحی و جلوگیری از entropy ضروری است.

---

# بخش هفتم — Design Language و کنترل‌های ظاهری

## 26. Button / Badge / Tag / Ribbon یک خانواده‌ی بصری مشترک دارند

این عناصر نباید هر کدام جهان بصری بی‌ربطی داشته باشند.

Global Design System برای آن‌ها language مشترک تعیین می‌کند، مانند:

- radius language
- border language
- shadow language
- accent treatment
- typography treatment
- motion language

مثال:

اگر Template دارای rounded-soft language باشد، Button/Badge/Tag/Ribbon پیش‌فرض نیز باید coherent باشند.

---

## 27. هماهنگی پیش‌فرض است، قفل مطلق نیست

Global family پیش‌فرض روی سراسر storefront اعمال می‌شود.

اما در Componentهایی که schema اجازه می‌دهد، Merchant می‌تواند local override داشته باشد.

Local override باید:

- typed باشد؛
- در Preview قابل تشخیص باشد؛
- قابل reset به Global/Template باشد؛
- با تغییر Global بی‌دلیل پاک نشود.

---

## 28. Preset-first، Advanced-second

رابط عادی باید choices ساده و قابل‌فهم نشان دهد.

مثال:

### Radius

- بدون گردی
- کم
- متوسط
- زیاد
- کاملاً گرد

### Shadow

- بدون سایه
- نرم
- متوسط
- برجسته

### Spacing

- فشرده
- معمولی
- باز

در **تنظیمات بیشتر**، Componentهایی که اجازه می‌دهند می‌توانند مقدار دقیق‌تر ارائه کنند.

اصل:

> **سادگی پیش‌فرض، قدرت در دسترس.**

Advanced mode نیز مجوز arbitrary CSS نیست؛ همچنان typed schema دارد.

---

# بخش هشتم — Responsive و Media

## 29. Responsive عمدتاً خودکار است

Merchant عادی نباید سه فروشگاه Desktop/Tablet/Mobile جدا طراحی کند.

Componentها و Design System باید خودشان:

- typography را responsive کنند؛
- grid را تطبیق دهند؛
- spacing را مناسب کنند؛
- Hero را برای mobile سازگار کنند؛
- columns را کاهش دهند؛
- bottom navigation مناسب را فعال کنند؛
- image behavior را حفظ کنند.

کاربر عادی نباید breakpoint یا media query ببیند.

Design Lab می‌تواند برای QA/compare viewportهای Desktop/Tablet/Mobile را نشان دهد، اما این «mobile override builder» نیست.

---

## 30. Crop تصویر باید ساده باشد

Default experience:

> **عکس را انتخاب کن و تمام.**

سیستم crop/fit مناسب جایگاه را انتخاب می‌کند.

اگر نتیجه مطلوب نبود، action ساده‌ی:

> **تنظیم تصویر**

می‌تواند drag/zoom/focal adjustment ساده بدهد.

Merchant نباید مجبور به فهم aspect ratio، object-position یا ساخت دستی چند نسخه شود.

---

## 31. Media Picker واحد

Hero، Banner، Category، Brand، Story، Logo و سایر نقاط تصویری باید یک Media Picker مشترک داشته باشند.

حداقل flow:

1. Upload from computer
2. Select from existing store media library
3. Simple image adjustment if needed

این Picker نباید برای هر section implementation جداگانه و UX متفاوت داشته باشد.

---

# بخش نهم — Home، Product Detail و سایر صفحات

## 32. Home مرکز اصلی آزادی طراحی است

Home آزادترین سطح Builder است.

Merchant می‌تواند از sectionهای ثبت‌شده و امن RastiSi:

- add
- remove
- reorder
- repeat
- configure content
- configure visual treatment
- edit parent/child
- apply local overrides

نمونه sectionها:

- Hero
- Category Grid
- New Products
- Best Sellers
- Discounted Products
- Collection
- Brands
- Festival/Campaign
- Banner
- Story
- Blog/Magazine
- Newsletter
- Trust/Shipping/Returns

هیچ arbitrary HTML/CSS/JS section در این سطح وجود ندارد.

---

## 33. Product Detail آزادی هدایت‌شده دارد

Product Detail نباید به Builder دوم شبیه Home تبدیل شود.

Merchant می‌تواند از layoutهای آماده انتخاب کند و controlهای اصلی داشته باشد، مانند:

- gallery presentation
- title/price information layout
- color/size selector presentation
- CTA presentation
- tabs/accordions
- related products
- FAQ/additional-information presentation where supported

اما:

- Product truth از Catalog/Commerce می‌آید؛
- structure آزاد Drag & Drop مانند Home ندارد؛
- component palette آن از Theme اصلی پیروی می‌کند مگر control مشخصی تعریف شده باشد.

---

## 34. سایر صفحات از Theme اصلی پیروی می‌کنند

صفحات زیر عمدتاً از Global Design System و Componentهای shared تبعیت می‌کنند:

- Category / Listing
- Search
- Brand
- Cart
- Account
- Blog listing
- Article
- About
- Contact
- سایر storefront pages آینده

تنظیمات page-specific باید حداقلی باشد و فقط وقتی ارزش محصولی روشن دارد اضافه شود.

هدف جلوگیری از تبدیل RastiSi به یک Page Builder پیچیده برای هر route است.

---

# بخش دهم — Header، Footer و Mega Menu

## 35. Header و Footer از مدل‌های آماده انتخاب می‌شوند

RastiSi مجموعه‌ی متنوعی از Header/Footerهای از قبل طراحی‌شده و registry-backed دارد/خواهد داشت.

Merchant آن‌ها را از gallery بصری انتخاب می‌کند.

Header/Footer از صفر با drag-and-drop ساخته نمی‌شوند.

---

## 36. شخصی‌سازی Header/Footer عمداً محدود است

پس از انتخاب مدل، فقط controlهای کم‌ریسک و پشتیبانی‌شده قابل تغییرند، مانند:

- logo
- background color token
- text/icon color token
- supported element toggles
- sticky when the selected Header supports it
- footer contact/social data coming from store information

عمداً محدود یا ممنوع:

- free-form drag & drop
- breaking structural composition
- arbitrary height edits
- arbitrary column restructuring
- independent complex font tuning for every child
- unlimited radius/shadow/spacing overrides

هدف:

> Header/Footer باید بعد از شخصی‌سازی Merchant همچنان design quality تضمین‌شده‌ی variant اصلی را حفظ کنند.

---

## 37. Mega Menu نیز model-first است

Mega Menu از میان variantهای آماده‌ی ثبت‌شده انتخاب می‌شود.

Merchant نباید مجبور شود Mega Menu را از صفر بسازد.

Content assignment می‌تواند بر اساس capabilities واقعی variant شامل category/brand/collection/page/link و در variantهای پشتیبانی‌شده promotional visual باشد؛ اما presentation structure از variant ثبت‌شده می‌آید.

جزئیات controlها باید از inventory واقعی Mega Menuهای موجود استخراج شود، نه با ساخت architecture موازی.

Mega Menu selection باید با capabilityهای Header انتخاب‌شده server-side validate شود.

---

# بخش یازدهم — Product Sections، Catalog و Commerce

## 38. Product Section دو حالت انتخاب محتوا دارد

### Automatic

مثال:

- newest
- best sellers
- discounted
- category-based
- brand-based
- rule-based related products

### Manual

Merchant محصولات را انتخاب و ترتیب آن‌ها را مشخص می‌کند.

در هر دو حالت:

- price از Catalog/Commerce؛
- stock از Catalog؛
- real discount از Promotion/Commerce؛
- Builder فقط selection/order/presentation را کنترل می‌کند.

---

## 39. Product Image در Builder منبع حقیقت نمی‌شود

Builder نباید ProductImage اصلی را مستقیماً mutate کند.

وقتی Merchant روی Product Image در context محصول کلیک می‌کند، باید shortcut واضحی مانند:

> **مدیریت تصاویر این محصول**

وجود داشته باشد.

این action کاربر را به source-of-truth product management هدایت می‌کند.

Builder می‌تواند نحوه‌ی نمایش image را تغییر دهد، نه catalog asset اصلی را.

---

## 40. Campaign / Festival / Timed Offer

Builder presentation را کنترل می‌کند:

- show/hide campaign section
- banner/image
- visual theme
- layout
- countdown style
- connection to a real Promotion

Commerce/Promotion truth را کنترل می‌کند:

- valid discount price
- start/end
- stock
- campaign rules
- eligibility
- active/expired truth

Timed-offer truth هرگز در Appearance ساخته نمی‌شود.

پس از expiry:

- countdown حذف می‌شود؛
- temporary discount دیگر active نمایش داده نمی‌شود؛
- product می‌تواند همچنان visible باشد؛
- normal commerce state نمایش داده می‌شود.

---

# بخش دوازدهم — Design Lab

## 41. Design Lab چیست؟

Design Lab یک surface پیشرفته و اختیاری برای کشف combinatorial power همان Store Appearance library است.

Design Lab می‌تواند ارائه کند:

- Ready Templates
- Header
- Mega Menu
- Hero
- Layout
- Product View
- Product Card
- Badge / design-language options
- Motion
- Footer
- Mobile Bottom Navigation
- Palette/Typography/Density/Radius/Width
- campaign/occasion overlays where supported
- Compare
- Desktop/Tablet/Mobile preview
- Random Mix
- per-family locks
- return to original DNA

اما Design Lab:

- renderer دوم نیست؛
- Builder production دوم نیست؛
- persistence model دوم نیست؛
- مجوز arbitrary HTML/CSS/JS نیست.

---

## 42. Transient Lab State

Lab exploration نباید برای هر click Draft mutation دائمی بسازد.

مدل:

```text
Lab UI
  -> transient typed Lab state
  -> server-side validation
  -> ephemeral Preview Manifest
  -> shared R4 renderer
```

browser می‌تواند transient state را برای usability موقت نگه دارد، اما تا Apply production state نیست.

`iframe.srcdoc`، cloned HTML یا renderer مستقل ممنوع است.

استفاده از iframe URL به shared Preview route، در صورتی که همان renderer production را استفاده کند، از نظر معماری مجاز است؛ ممنوعیت مربوط به renderer/HTML مستقل است.

---

## 43. Apply from Design Lab

وقتی Merchant Apply را می‌زند:

1. full candidate manifest server-side validate می‌شود؛
2. tenant scope و stale-write/version preconditions چک می‌شوند؛
3. candidate به یک logical/atomic Draft mutation تبدیل می‌شود؛
4. merchant content/catalog/business data حفظ می‌شود؛
5. operation وارد history عادی می‌شود.

صدها experiment در Lab نباید صدها Draft history entry بسازند.

---

# بخش سیزدهم — Compatibility و Recommendation

## 44. Compatibility metadata

Library باید compatibility metadata سبک داشته باشد برای:

- Ready Template curation
- Design Lab recommendations
- Random Mix
- Builder recommendation ordering
- QA warnings

اصل:

- guidance first؛
- blocking فقط برای incompatibility واقعی و functional؛
- aesthetic recommendation نباید آزادی technically valid Merchant را بی‌دلیل قفل کند.

مثال مهم:

Mega Menu باید با capabilityهای Header انتخاب‌شده سازگار باشد.

---

# بخش چهاردهم — Canonical Demo Store

## 45. Rasti Mode Demo منبع ثابت QA و نمایش توان سیستم است

Canonical fixture:

```text
Rasti Mode Demo
slug: rasti-mode-demo
```

Demo باید از همان models/contracts/renderer واقعی Merchant استفاده کند.

هیچ demo-only renderer یا hardcoded template path نباید وجود داشته باشد.

---

## 46. Demo باید یک فروشگاه کامل و واقعی‌نما باشد

Demo باید توان storefront را با محتوای غنی نمایش دهد، از جمله:

- logo/favicon
- multiple Heroes
- promotional banners
- categories
- brands
- stories
- products with realistic imagery/variants
- collections
- new/best-selling/discount sections
- festival/timed-offer examples
- blog/magazine
- newsletter
- trust/shipping/returns
- complete Footer
- Product Detail state

canonical content baseline برای مقایسه‌ی تمام 50 template باید تا حد ممکن ثابت باشد تا تفاوت template واقعاً تفاوت design باشد.

---

## 47. Demo Content Pack و Merchant Data جدا هستند

Demo می‌تواند با seed/refresh command کامل شود.

اما:

- Template selection Demo products را copy نمی‌کند؛
- Merchant store fake Demo categories/brands/prices دریافت نمی‌کند؛
- Template فقط design recipe است؛
- پس از Merchant onboarding، template preview در صورت امکان باید با data خود Merchant هم قابل مشاهده باشد.

---

# بخش پانزدهم — Security و Validation

## 48. فقط typed و registered values

Persisted appearance می‌تواند فقط شامل:

- registered component keys
- typed enum/token values
- schema-validated numbers/strings/resources
- tenant-scoped references

باشد.

Forbidden:

- arbitrary HTML
- arbitrary CSS
- JavaScript
- executable expressions
- unrestricted raw JSON
- arbitrary file/template paths
- arbitrary renderer names
- cross-tenant asset IDs

Client validation برای UX کافی نیست؛ server validation الزامی است.

---

## 49. Tenant safety

هر resource reference مانند image/media/product/collection/brand باید در store/tenant scope validate شود.

Invalid component key یا incompatible key باید typed error بدهد و silent fallback خطرناک نداشته باشد.

برای component family جدید باید safe default/off state وجود داشته باشد تا storeهای قدیمی شکسته نشوند.

---

# بخش شانزدهم — Versioning و Extensibility

## 50. Versioning

Stable bug fix می‌تواند implementation همان key را اصلاح کند اگر visual/behavior contract materially نشکند.

Material redesign باید version/key جدید بگیرد.

Ready Templateها schema version دارند؛ baseline:

```text
schema_version = 1
```

Template historical versions باید قابل resolve/restore باشند اگر Draft/Published state به آن‌ها reference دارد.

---

## 51. افزودن Component family آینده

افزودن family جدید نباید نیازمند:

- rewrite تمام 50 template؛
- Draft lifecycle جدید؛
- renderer دوم؛
- Builder دوم؛
- duplicate registries؛

باشد.

Family جدید باید از همان contracts، safe default، validation، renderer و responsive behavior استفاده کند.

---

# بخش هفدهم — Performance و Maintenance

## 52. Shared implementations، lightweight state

هزاران Merchant می‌توانند به همان Component implementation reference بدهند.

RastiSi implementation را per-store copy نمی‌کند.

اصول:

- deterministic registry lookup
- shared static assets
- cache keyed by immutable/versioned appearance/layout state where safe
- tenant-safe cache boundaries
- no runtime filesystem discovery for merchant-selected renderer
- no arbitrary dynamic imports
- no duplicated per-template CSS/JS bundles when shared assets suffice
- debounced/cancellable Design Lab preview requests
- Preview/Public cache identity aware of Draft vs Published versions

---

# بخش هجدهم — 50 Ready Templates: Curation و Diversity

## 53. دقیقاً 50 قالب رسمی در این initiative

این phase دقیقاً 50 Ready Template رسمی دارد.

Template marketplace عمومی یا candidate-template subsystem نامحدود خارج از scope این initiative است.

Design directions می‌توانند شامل:

- minimal/clean
- luxury/premium
- dense marketplace
- editorial/magazine
- modern/technology
- warm/boutique
- bold/colorful
- Hero-led
- promotion/countdown-led
- mobile/social-commerce-led

باشند.

این‌ها tag/curation direction هستند، نه codebase یا technical family جدا.

---

## 54. Diversity gate

Template جدید فقط با palette/font متفاوت، Template واقعاً جدید محسوب نمی‌شود.

تمایز باید در چند dimension عمده دیده شود، مانند:

- Header composition
- Hero composition
- section sequence/composition
- Product View
- Product Card geometry
- density/rhythm
- Footer
- Mobile Bottom Navigation
- typography treatment
- motion language
- distinctive reusable variants

Palette-only/font-only variation gate را پاس نمی‌کند.

---

## 55. Component coverage matrix

Componentهای production advertised باید در حد امکان در حداقل یک Ready Template curated استفاده شوند، مگر exception مستند و تأییدشده.

Coverage matrix باید نشان دهد:

- componentهای unused؛
- familyهای کم‌پوشش؛
- combinationهای بدون QA؛
- variantهایی که شاید unnecessary یا poorly integrated باشند.

---

# بخش نوزدهم — QA و Release Gates

## 56. QA هر Component

Evidence متناسب با capability باید شامل موارد زیر باشد:

- registry/contract validation
- schema validation
- renderer resolution
- invalid-key safety
- Desktop/Tablet/Mobile behavior
- RTL
- short/long content
- image variations
- accessibility/interactions where relevant
- normal/sale/timed-offer states where relevant
- no unexpected console/request/render errors

---

## 57. QA هر Ready Template

هر یک از 50 Template باید روی canonical Demo Store رندر و بررسی شود.

حداقل visual review:

- Desktop
- Mobile

Tablet در automated responsive/component coverage و هرجا structure نیاز دارد در visual review.

هر Template باید ثابت کند:

- shared renderer parity دارد؛
- registry reference شکسته ندارد؛
- combination unsupported ندارد؛
- RTL/responsive قابل قبول است؛
- به Demo data coupling ناخواسته ندارد؛
- از Templateهای دیگر به‌قدر کافی متمایز است؛
- Header/Footer/BottomNav درست کار می‌کنند؛
- representative commerce states درست نمایش داده می‌شوند.

Template‌ای که Preview/Design Lab آن از renderer متفاوت Public استفاده کند complete نیست.

---

## 58. QA Direct Editor و Content Hub

علاوه بر visual QA، flowهای UX جدید باید تست شوند:

- click element -> correct context panel
- parent/child navigation
- tab capability filtering
- local override persistence
- reset to parent/template
- live preview parity
- autosave Draft
- no Public mutation before Publish
- stale-write rejection
- Undo/Redo/Restore
- Media Picker reuse
- template switch preserving merchant content
- section add/remove/reorder/repeat
- automatic/manual product section selection
- Header/Footer protected-controls enforcement
- product-image management shortcut without Builder source-of-truth mutation

---

# بخش بیستم — Explicit Non-goals

## 59. این معماری عمداً شامل موارد زیر نیست

- 50 codebase جدا؛
- Builder جدا برای هر Template؛
- renderer جدا برای Design Lab؛
- renderer جدا برای Demo؛
- arbitrary merchant HTML/CSS/JS؛
- raw executable JSON؛
- Draft lifecycle جدا برای هر Component؛
- Mobile Builder جدا؛
- Page Builder کاملاً آزاد برای تمام routeها؛
- Product Detail آزاد مانند Home؛
- Header/Footer free-form drag-and-drop؛
- Mega Menu builder آزاد از صفر؛
- تغییر price/stock/SKU/order از Storefront Builder؛
- copy کردن Demo catalog به Merchant هنگام Template apply؛
- lock دائمی Merchant به Template اولیه؛
- public template marketplace در این phase؛
- candidate-template persistence نامحدود در این phase.

---

# بخش بیست‌ویکم — 26 تصمیم محصول قفل‌شده

## 60. Decision Register

این 26 تصمیم بخشی از architecture contract هستند:

1. Direct Editing و Content Hub هر دو وجود دارند؛ Direct Editing مسیر طبیعی و اصلی است.
2. Builder ظاهر و محتوای نمایشی را ویرایش می‌کند، نه Commerce truth.
3. Product image در Catalog مدیریت می‌شود؛ Builder shortcut می‌دهد.
4. Product sections هم automatic و هم manual selection دارند.
5. Draft autosave + live Preview + explicit Publish.
6. Home sectionها قابل add/remove/reorder/repeat هستند، فقط از registry امن.
7. Template switch به‌طور پیش‌فرض design DNA را عوض می‌کند و merchant content/custom structure را حفظ می‌کند.
8. Builder campaign presentation را کنترل می‌کند؛ Promotion/Commerce truth را.
9. تجربه‌ی اصلی: click مستقیم روی چیزی که دیده می‌شود.
10. تغییر معتبر بدون Apply button روزمره فوراً در Preview دیده می‌شود.
11. child به‌صورت دقیق انتخاب می‌شود و parent در همان editor قابل دسترس است.
12. Undo/Redo/History/Revert-to-Published/Restore وجود دارد.
13. Responsive برای Merchant عادی خودکار است.
14. Crop default خودکار است و adjustment دستی ساده و اختیاری.
15. UI ساده به‌صورت پیش‌فرض، Advanced/More Settings برای power users.
16. Template defaults می‌دهد؛ section/elementهای مجاز local override دارند.
17. parent و child در editor tabbed/contextual در دسترس‌اند.
18. تغییر parent child override را پاک نمی‌کند.
19. Button/Badge/Tag/Ribbon از Design Language مشترک پیروی می‌کنند.
20. هماهنگی global پیش‌فرض است، local override در capabilityهای مجاز ممکن است.
21. controlهای ظاهری preset-first و advanced typed-second هستند.
22. Home آزادترین صفحه؛ Product Detail هدایت‌شده؛ بقیه صفحات Theme-driven.
23. Product Detail از layoutهای آماده + controls اصلی استفاده می‌کند.
24. Header/Footer از modelهای آماده انتخاب می‌شوند.
25. Header/Footer customization بسیار محدود و محافظت‌شده است.
26. Mega Menu نیز model-first و registry-backed است، نه ساخت آزاد از صفر.

---

# بخش بیست‌ودوم — Acceptance Criteria نهایی

## 61. معماری فقط وقتی صحیح اجرا شده که همه‌ی موارد زیر برقرار باشند

1. یک Store Appearance logical subsystem روی registries/contracts موجود وجود داشته باشد، نه duplicate registry stack.
2. Merchant Draft validated component choices/settings نگه دارد، نه copied implementation code.
3. changing one component بتواند فقط همان component را mutate کند.
4. applying Ready Template یک preset operation صریح و typed باشد.
5. 50 Template recipe روی shared engine باشند، نه application مستقل.
6. همه‌ی 50 Template برای همه‌ی industries در دسترس باشند؛ industry فقط ranking/recommendation را تغییر دهد.
7. Template switch merchant content/catalog/business truth را حفظ کند.
8. custom Home structure در template switch به‌طور پیش‌فرض حفظ شود؛ reset-to-template-structure action صریح باشد.
9. Template Demo content هرگز هنگام preset apply به Merchant catalog copy نشود.
10. Direct Preview Editor و Content Hub روی همان source of truth کار کنند.
11. click روی element context درست همان element را باز کند و parent navigation داشته باشد.
12. editor tabs فقط controls مرتبط با capability واقعی component را نشان دهند.
13. child overrides با parent change حفظ شوند و reset mechanism واضح داشته باشند.
14. Header/Footer/Mega Menu model-first و protected باشند.
15. Home safe registered sections را add/remove/reorder/repeat کند بدون arbitrary code.
16. Product Detail controlled layout/presentation options داشته باشد، نه free-form builder.
17. سایر storefront pages عمدتاً از Theme/Global Design تبعیت کنند.
18. Product section automatic/manual selection داشته باشد ولی price/stock truth را mutate نکند.
19. Product images از Catalog source-of-truth مدیریت شوند.
20. Timed-offer truth در Commerce باشد و Appearance فقط presentation کند.
21. Live Preview و Draft autosave وجود داشته باشد؛ Public فقط Publish.
22. Undo/Redo/History/Revert/Restore کار کند.
23. Responsive برای Merchant عادی خودکار باشد و Mobile Builder جدا وجود نداشته باشد.
24. Media Picker واحد برای appearance/content images reuse شود.
25. Design Lab transient typed state و shared renderer استفاده کند.
26. Apply from Lab یک logical/atomic validated Draft operation با stale-write protection باشد.
27. `iframe.srcdoc` یا cloned independent renderer در production Design Lab/Preview وجود نداشته باشد.
28. invalid/unknown component keys server-side رد شوند.
29. arbitrary HTML/CSS/JS/raw executable JSON/template paths ممنوع باشند.
30. tenant-scoped resources server-side validate شوند.
31. future component families با safe default اضافه شوند بدون rewrite تمام 50 template.
32. material component redesign version/key جدید بگیرد.
33. Rasti Mode Demo canonical content fixture برای comparison/QA باشد و shared renderer واقعی را استفاده کند.
34. همه‌ی 50 Template responsive/shared-renderer/diversity/coverage gates را پاس کنند.
35. palette/font-only variation به‌تنهایی Template جدید محسوب نشود.
36. normal Builder complexity موتور combinatorial را به Merchant عادی تحمیل نکند.
37. Button/Badge/Tag/Ribbon coherent design language داشته باشند.
38. Advanced settings نیز typed و safe باشند، نه راهی برای arbitrary CSS.
39. Public rendering همان normal R4 Publish lifecycle را حفظ کند.
40. هر feature آینده‌ای که این invariants را بشکند نیازمند تصمیم معماری صریح جدید باشد.

---

# بخش بیست‌وسوم — Mental Model برای تیم توسعه و محصول

## 62. اگر فقط پنج جمله از این سند به خاطر بماند

1. **ما 50 فروشگاه جدا نداریم؛ یک engine و 50 DNA حرفه‌ای داریم.**
2. **Merchant باید فروشگاه را با کلیک روی چیزی که می‌بیند ویرایش کند، نه با فهمیدن معماری داخلی.**
3. **Commerce truth از Builder جداست؛ Builder presentation و display content را کنترل می‌کند.**
4. **Template defaults می‌دهد، local overrideها را می‌پذیرد، اما Header/Footer/Mega Menu عمداً محافظت‌شده‌ترند.**
5. **Preview، Public، Design Lab و Demo همگی باید به یک renderer و یک مجموعه‌ی contracts واقعی ختم شوند.**

---

# 63. Final Product Statement

> **RastiSi یک Storefront Appearance Engine قابل‌گسترش و مشترک می‌سازد که از تعداد زیادی Component حرفه‌ای و نسخه‌دار تشکیل شده و 50 Ready Template رسمی، coherent و تست‌شده را به‌عنوان نقطه شروع ارائه می‌کند. صاحب فروشگاه در تجربه‌ی روزمره لازم نیست این موتور را بفهمد: او فروشگاه را می‌بیند، روی عنصر موردنظر کلیک می‌کند، فقط تنظیمات مرتبط همان عنصر و والدش را در یک editor تب‌دار می‌بیند، تغییر را به‌صورت زنده مشاهده می‌کند و Draft به‌طور خودکار ذخیره می‌شود. Home آزادی بالایی دارد؛ Product Detail هدایت‌شده است؛ سایر صفحات از Theme پیروی می‌کنند؛ Header/Footer/Mega Menu از variantهای آماده و محافظت‌شده انتخاب می‌شوند. محتوای Merchant و حقیقت تجاری مستقل از Template باقی می‌مانند. Design Lab، Content Hub، Preview، Demo و Public همگی روی همان contracts و همان shared renderer کار می‌کنند.**

این سند باید مرجع اصلی هر تصمیم بعدی درباره‌ی Storefront Builder و Store Appearance باشد. هر implementation plan باید بتواند trace کند که هر task کدام بخش و کدام acceptance criterion این سند را محقق می‌کند.
