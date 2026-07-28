# سند مرجع جامع پروژه فروشگاه‌ساز اخلاقی

> **نام پیشنهادی در Repository:** `docs/00_PROJECT_MASTER_REFERENCE.md`<br>
> **وضعیت سند:** مرجع راهبردی و فنی فعال<br>
> **نسخه:** 1.0<br>
> **تاریخ وضعیت:** پس از Merge شدن PR #21<br>
> **پروژه:** CLOAUD-AKHLAGHI<br>
> **نوع محصول:** پلتفرم فروشگاه‌ساز چندمستاجره مبتنی بر Django<br>
> **نخستین فروشگاه واقعی:** اخلاقی (`Akhlaghi`)<br>
> **زبان اصلی محصول:** فارسی، راست‌چین، موبایل‌محور<br>
> **وضعیت فعلی:** زیرساخت چندمستاجری و مرز کاتالوگ تثبیت شده؛ تطبیق قابلیت‌های واقعی Repository با نقشه محصول در جریان است.

---

# 1. هدف این سند

این سند باید نقطه شروع هر توسعه‌دهنده، معمار، بازبین فنی، مدیر محصول و عامل هوش مصنوعی باشد که وارد پروژه می‌شود.

اهداف اصلی:

1. تعریف دقیق ماهیت محصول؛
2. جلوگیری از بازگشت پروژه به معماری تک‌فروشگاهی؛
3. ثبت وضعیت واقعی پیاده‌سازی تا پایان PR #21؛
4. تفکیک «کد موجود» از «تصویر مقصد محصول»؛
5. تثبیت تصمیم‌های معماری پذیرفته‌شده؛
6. ارائه نقشه شکاف میان Repository و خروجی‌های استخراج‌شده از صفحات مرجع MixIn؛
7. تعریف اولویت‌های توسعه، معیارهای پذیرش و قواعد اجرای PRهای بعدی؛
8. جلوگیری از ساخت قابلیت‌های نمایشی بدون مرز امنیتی، داده‌ای و عملیاتی معتبر.

این سند نباید به‌تنهایی جای کد، Migration، Test یا ADR را بگیرد. هر ادعا درباره رفتار جاری باید با Repository، تست‌های سبز و Migrationهای واقعی تأیید شود.

---

# 2. سلسله‌مراتب منابع حقیقت

در صورت اختلاف میان منابع، ترتیب اعتبار زیر الزامی است:

1. **کد Production موجود در Repository**
2. **Migrationهای اعمال‌شده**
3. **تست‌های سبز و تست‌های adversarial**
4. **ADRها و اسناد معماری فعال Repository**
5. **این سند**
6. **گزارش‌های تحلیل Repository**
7. **خروجی‌های استخراج‌شده از MixIn و سایر نمونه‌های مرجع**
8. **طرح‌های تصویری، HTMLهای مرجع و ایده‌های محصولی**
9. **گفتگوها و پیشنهادهای عامل‌های هوش مصنوعی**

نتیجه مهم:

> صفحات HTML استخراج‌شده از MixIn، مرجع قابلیت، معماری اطلاعات و تجربه کاربری هستند؛ نه قرارداد مستقیم Backend، مدل داده، URL یا مجوزهای این پروژه.

هیچ مدل، App، Route، تکنولوژی یا Workflow صرفاً به دلیل وجود در اسناد مرجع نباید وارد Repository شود.

---

# 3. تعریف رسمی محصول

## 3.1 محصول چیست؟

این پروژه یک وب‌سایت فروشگاهی منفرد برای اخلاقی نیست.

این پروژه یک **پلتفرم فروشگاه‌ساز چندمستاجره** است که:

- چند فروشگاه مستقل را در یک سامانه میزبانی می‌کند؛
- هر فروشگاه Domain، تنظیمات، کاتالوگ، محتوا، مشتریان، سفارش‌ها، پرداخت‌ها و عملیات خود را دارد؛
- اطلاعات هیچ فروشگاهی نباید برای فروشگاه دیگر قابل خواندن، تغییر یا استنتاج باشد؛
- اخلاقی اولین Tenant واقعی و مرجع عملیاتی محصول است؛
- محصول باید در آینده برای صنایع متفاوت قابل فروش باشد؛ از جمله:
  - تأسیسات و HVAC؛
  - لوازم خانگی؛
  - قطعات خودرو؛
  - شمع و محصولات تزئینی؛
  - میوه و سبزیجات؛
  - فروشگاه‌های عمومی و تخصصی.

## 3.2 اصل پلتفرم‌محور

تمام تصمیم‌های جدید باید با این سؤال سنجیده شوند:

> آیا این تصمیم برای یک Store عمومی در پلتفرم درست است، یا فقط برای فروشگاه اخلاقی کار می‌کند؟

ممنوع:

- فرض دائمی وجود فقط یک Store؛
- استفاده از `pk=1`؛
- استفاده از `.first()` برای تشخیص Store؛
- fallback پنهان به Akhlaghi در runtime؛
- استفاده از Vendor به‌عنوان Tenant؛
- اعتماد به `store_id` ارسال‌شده از Browser؛
- Queryهای Storeless روی داده merchant-created؛
- cache key، فایل، Session یا Job بدون Store identity.

---

# 4. واژگان رسمی پروژه

| واژه | تعریف رسمی |
|---|---|
| Platform | کل سامانه فروشگاه‌ساز |
| Store | مرز اصلی Tenant و مالک داده فروشگاه |
| StoreDomain | نگاشت Host/Domain تأییدشده به Store |
| Akhlaghi | اولین Store واقعی؛ نه Store پیش‌فرض عمومی |
| Merchant | کسب‌وکار استفاده‌کننده از پلتفرم |
| Merchant Operator | کاربر عملیاتی پنل اختصاصی فروشگاه |
| Platform Superuser | مدیر کل پلتفرم با دسترسی Django Admin |
| Custom Dashboard | پنل merchant در مسیر `/admin-panel/` |
| Django Admin | ابزار عملیات پلتفرم در مسیر `/admin/` |
| Aggregate Root | مدلی که مالکیت Store و lifecycle مستقل دارد |
| Store-owned Child | مدل فرزندی که مالکیت را از Parent معتبر به ارث می‌برد |
| Platform-global | داده‌ای که عمداً میان همه Storeها مشترک است |
| Store Context | Store authoritative که از Host یا Aggregate معتبر به دست آمده |
| Target Vision | قابلیت‌ها و UX مقصد، استخراج‌شده از MixIn و اسناد مرجع |
| Implemented | موجود در کد، تست‌شده و Merge‌شده |
| Partial | بخشی موجود است ولی قرارداد کامل هدف را پوشش نمی‌دهد |
| Deferred | آگاهانه به PR یا فاز آینده منتقل شده |
| Absent | هنوز در Repository پیاده‌سازی نشده |

---

# 5. وضعیت تأییدشده Repository تا پایان PR #21

## 5.1 خط مبنا

بر اساس آخرین گزارش Merge‌شده:

- Branch اصلی عملیاتی: `claude/project-phase-zero-duumj5`
- PR #21 Merge و بسته شده است.
- Test suite پس از Remediation:
  - **1535 passed**
  - **0 failed**
  - **0 errors**
  - **0 skipped**
- `manage.py check`: پاک
- `makemigrations --check --dry-run`: بدون Drift
- Django Admin برای کاربران merchant بسته شده و فقط Platform Superuser به آن دسترسی دارد.

توجه: هر توسعه‌دهنده باید پیش از کار، این وضعیت را از HEAD فعلی Repository دوباره تأیید کند؛ اعداد فوق Snapshot تاریخی این سند هستند.

## 5.2 PRهای بنیادین چندمستاجری

### PR #19 — Store-scoped Core Settings

نتیجه:

- تنظیمات اصلی فروشگاه از Singleton سراسری خارج شدند؛
- Store به مرز مالکیت تنظیمات تبدیل شد؛
- الگوهای Singleton پنهان کاهش یافتند؛
- Akhlaghi به‌عنوان داده Migration تاریخی استفاده شد، نه fallback runtime.

### PR #20 — Explicit Store Context Propagation

نتیجه:

- Pricing و SMS در لایه leaf به `HttpRequest` وابسته نیستند؛
- Store به‌صورت صریح به سرویس‌ها داده می‌شود؛
- Management commandها Store را صریح resolve می‌کنند؛
- Serviceهای پایین‌دست Store را از Request، Global Singleton یا Akhlaghi حدس نمی‌زنند.

قاعده تثبیت‌شده:

```text
HTTP Boundary → resolve Store once → pass store explicitly
Domain Aggregate → derive Store from authoritative aggregate
Background/Command → resolve Store explicitly from durable identity
```

### PR #21 — Catalog Tenant Boundary Assessment and Hardening

نتیجه:

- Vendor، Category، Brand و Product مالک مستقیم Store هستند؛
- ProductVariant دارای Store denormalized و guardهای application-level است؛
- ProductImage، Specification و Review مالکیت را از Product به ارث می‌برند؛
- Slug و SKUهای merchant-facing به‌صورت per-Store مدیریت می‌شوند؛
- Storefront، Search، Wishlist و Dashboard Catalog ایزوله شده‌اند؛
- Mixed-Store Cart نمی‌تواند Order ایجاد کند؛
- Dashboard statistics محصولات Storeهای دیگر را ترکیب نمی‌کند؛
- crafted POST برای relationهای Cross-Store رد می‌شود؛
- مسیر Django Admin فقط برای Platform Superuser باز است؛
- تغییر Parent یا Store در ProductVariant از طریق `update` و `bulk_update` مسدود شده است.

---

# 6. معماری فعلی سطح بالا

```text
Client / Browser
        │
        ▼
Host / Domain Resolution
        │
        ▼
StoreDomain → Store
        │
        ├── Storefront
        │     ├── Catalog
        │     ├── Cart
        │     ├── Checkout
        │     ├── Customer Account
        │     └── Content
        │
        ├── Merchant Dashboard (/admin-panel/)
        │     └── is_active + is_staff
        │
        └── Platform Admin (/admin/)
              └── is_active + is_superuser
```

معماری برنامه همچنان یک **Modular Monolith** مبتنی بر Django است. این انتخاب در مرحله فعلی صحیح است؛ زیرا:

- دامنه‌ها هنوز در حال تثبیت‌اند؛
- تراکنش‌های Order، Payment، Inventory و Content نیازمند consistency درون‌برنامه‌ای‌اند؛
- تیم و Workflow پروژه برای Microservice آماده نیست؛
- جداسازی منطقی Appها و Serviceها برای رشد آینده کافی است.

ساخت Microservice، Event Bus خارجی یا distributed transaction در این مرحله ممنوع است مگر با ADR و نیاز اثبات‌شده.

---

# 7. نقشه Appهای فعلی و نقش هدف آن‌ها

| App فعلی | مسئولیت جاری | حوزه هدف | تصمیم |
|---|---|---|---|
| `stores` | Store، Domain resolution، membership foundation، admin gate | Tenancy/IAM | App رسمی Tenant؛ Rename نشود |
| `core` | تنظیمات اصلی، ابزارها، theme tokenها، seed | Store settings / kernel utilities | کد merchant-specific باید Store-owned باشد |
| `catalog` | Product، Variant، Category، Brand، Media، Specification، Review | Catalog & sellable items | هسته Tenant boundary تثبیت شده |
| `cart` | Cart، CartItem، Coupon، pricing | Cart/Pricing/Promotion | Tenantization کامل نشده |
| `orders` | Checkout، Order، ShippingMethod، PaymentGateway، Transaction | Orders/Payment/Shipping | نیازمند audit و ownership کامل |
| `customers` | Customer، Address، Wishlist، Auth/OTP | Customer/IAM | Store ownership کامل نشده |
| `content` | Hero، Banner، Menu، Page، Footer، Social links | CMS/Navigation/Appearance | relationهای Storeless باقی مانده |
| `blog` | BlogPost | Content/SEO | Tenant boundary باید ممیزی شود |
| `sms` | Template، Log، OTP، provider | Messaging/Notification | Store context بهتر شده؛ hardening ناقص |
| `dashboard` | Merchant-facing admin panel | Merchant Operations | باید به‌تدریج StoreMembership-aware شود |

قانون:

> Appهای پیشنهادی اسناد مرجع مانند `tenancy`، `messaging`، `theming` یا `payments` نباید بدون دلیل ساخته شوند اگر App موجود همان مسئولیت را پوشش می‌دهد.

---

# 8. مدل مالکیت داده

## 8.1 طبقه‌بندی اجباری

هر مدل جدید باید در یکی از چهار دسته قرار گیرد:

### A. Platform-global

تنها برای داده‌ای مجاز است که:

- توسط پلتفرم کنترل می‌شود؛
- merchant-created نیست؛
- محتوای حساس فروشگاهی ندارد؛
- عمداً میان همه Storeها مشترک است.

نمونه‌های احتمالی:

- Registry ثابت کشور یا استان؛
- تعریف providerهای پلتفرمی؛
- permission registry سراسری.

### B. Store-owned Aggregate Root

مدلی با lifecycle، Query یا Mutation مستقل.

معمولاً نیازمند direct `store` FK است.

نمونه‌های تأییدشده:

- Vendor
- Category
- Brand
- Product

کاندیداهای آینده:

- Customer
- Cart
- Coupon
- Order
- PaymentGateway configuration
- ShippingMethod
- ContentPage
- Menu
- BlogPost
- SmsTemplate

### C. Store-owned Child Through Parent

مدل بدون direct Store FK که:

- Parent authoritative واحد دارد؛
- تمام Queryها از Parent Store-scoped عبور می‌کنند؛
- lifecycle مستقل ندارد؛
- cross-parent attachment قابل ایجاد نیست.

نمونه‌های تأییدشده:

- ProductImage → Product → Store
- Specification → Product → Store
- Review → Product → Store

### D. Redundant Store-owned Child

direct Store FK تنها در صورت نیاز اثبات‌شده برای:

- Query مستقل پرتکرار؛
- uniqueness per-Store؛
- Job/Import؛
- permission boundary؛
- performance یا constraint.

نمونه فعلی:

- ProductVariant

در این حالت باید دو منبع مالکیت کنترل شوند:

```text
child.store == child.parent.store
```

اگر DB cross-table constraint ممکن نیست، تمام Mutation pathها باید guard شوند و محدودیت application-enforced صریحاً مستند شود.

---

# 9. اصول Store Resolution و Tenant Isolation

## 9.1 Host authoritative است

در مسیر HTTP:

1. Host درخواست دریافت می‌شود؛
2. Domain normalize می‌شود؛
3. StoreDomain معتبر resolve می‌شود؛
4. Store فعال و مجاز مشخص می‌شود؛
5. `request.store` فقط در Boundary ایجاد می‌شود؛
6. Store به Serviceهای پایین‌دست داده می‌شود.

ممنوع:

- دریافت Store از POST؛
- دریافت Store از Query string؛
- انتخاب Store با `.first()`؛
- fallback به Store قدیمی؛
- Trust کردن Session بدون تطبیق Host؛
- Resolve دوباره Store در leaf service.

## 9.2 رفتار Fail-closed

- Host ناشناخته نباید به Store اخلاقی هدایت شود؛
- Domain تأییدنشده نباید داده Merchant نمایش دهد؛
- Store غیرفعال باید مطابق قرارداد resolver رد شود؛
- Cross-Store object lookup باید معمولاً `404` بدهد تا وجود Object افشا نشود؛
- کاربر authenticated ولی فاقد مجوز عملیاتی می‌تواند `403` بگیرد؛
- relation Cross-Store در Form/Service باید Validation Error تولید کند.

## 9.3 Middleware مرز Authorization کامل نیست

وجود `request.store` تنها Tenant را مشخص می‌کند. Authorization جداگانه باید بررسی کند:

- کاربر عضو همان Store است؛
- Role/Permission لازم را دارد؛
- عملیات در وضعیت مجاز است؛
- Object واقعاً متعلق به Store است.

---

# 10. مرز پنل Merchant و Django Admin

## 10.1 قرارداد فعلی

```text
/admin-portal/   (مسیر رسمی؛ /admin-panel/ صرفاً یک 302 redirect موقت به همین مسیر است)
    برای Merchant Operators
    gate فعلی: is_active + is_staff + عضویت StoreMembership فعال در Store resolve‌شده

/admin/
    برای Platform Superusers
    gate فعلی: is_active + is_superuser
```

این تفکیک یک کنترل موقت اما ضروری است.

## 10.2 محدودیت شناخته‌شده

`StoreMembership` هنوز به Authorization کامل Dashboard متصل نشده است. بنابراین:

- `is_staff` هنوز نقش Merchant را به‌صورت دقیق مدل نمی‌کند؛
- Roleهای OWNER، MANAGER، CATALOG، ORDER، CONTENT یا REPORTING باید در آینده مستقل شوند؛
- نباید با اضافه‌کردن ModelAdminهای Store-scoped، Django Admin را به Merchant Dashboard دوم تبدیل کرد؛
- Merchant operations باید در Custom Dashboard باقی بماند.

## 10.3 هدف آینده

```text
User
  └── StoreMembership
        ├── Store
        ├── Role
        ├── Status
        └── Permission keys
```

تمام Viewها و Serviceهای حساس باید علاوه بر Store isolation، permission key مناسب را enforce کنند.

> **الحاقیه (پس از PR — Order Boundary and Checkout Integrity، ۱۴۰۵/۰۵/۰۴):**
> این PR شکاف Store-isolation (نه شکاف نقش/Permission بالا) را برای
> سفارش/فاکتور/پرداخت/مشتری/درگاه/روش‌ارسال بست: `apps.dashboard.services.orders_admin_service`،
> `customers_admin_service`، و `settings_admin_service` اکنون همگی یک
> `store` صریح می‌گیرند (همان الگویی که در PR#21 برای کاتالوگ اعمال شد)،
> و اندپوینت‌های جزئیات/جهش (`order-detail`، `invoice-detail`،
> `customer-detail`، `settings-gateway-toggle`، `settings-shipping-toggle`)
> هرکدام مستقل عضویت Store را enforce می‌کنند — نه فقط صفحات فهرست. **این
> محدودیت §10.2 را برطرف نمی‌کند** — همچنان هر `is_staff=True` (بدون توجه
> به این‌که برای کدام Store) به `/admin-panel/` هر Store دسترسی دارد؛ این
> PR فقط تضمین می‌کند وقتی چنین کاربری به یک Store خاص از طریق Host وارد
> می‌شود، داده‌های Storeهای دیگر را نمی‌بیند — نه این‌که کدام کاربر اصلاً
> باید به کدام Store دسترسی داشته باشد. حل کامل §10.2 (`StoreMembership`
> role-based authorization) هنوز کار آینده است.

> **الحاقیه ۲ (پس از PR — Merchant Admin Authorization and Routing
> Foundation، «Phase 1B»):** این PR دقیقاً همان محدودیت §10.2 را که
> الحاقیهٔ بالا به‌صراحت باز گذاشته بود، می‌بندد:
> `apps.dashboard.decorators.staff_required` اکنون علاوه بر `is_staff`،
> یک `StoreMembership` با وضعیت `ACTIVE` دقیقاً برای همان Store resolve‌شده
> از Host را الزامی می‌کند (نه صرفاً عضویت در Store دیگر). یک رجیستری
> Permission دانه‌ریز جدید (`apps.stores.authorization`) نقش‌های موجود
> (`OWNER`، `ADMINISTRATOR`، `CATALOG_MANAGER`، `ORDER_MANAGER`،
> `CONTENT_EDITOR`، `ANALYST` — بدون افزودن نقش جدید) را به معنای واقعی
> Permission در ۸۳ View داشبورد متصل کرده؛ دسترسی نامجاز اکنون `403`
> واقعی (`dashboard/403.html`) برمی‌گرداند، نه فقط پنهان‌شدن دکمه در UI.
> ناوبری Sidebar نیز اکنون Permission-aware است (`apps.dashboard.context_processors.merchant_permissions`).
> مسیر رسمی Dashboard از `/admin-panel/` به `/admin-portal/` تغییر کرد
> (`/admin-panel/` اکنون صرفاً یک 302 redirect موقت است — نگاه کنید به
> ADR-16 در `SAAS_DOMAIN_DECISIONS.md`). یک زیردامنهٔ پایدار پنل مدیریت
> (`Store.admin_subdomain`، مستقل از `StoreDomain` عمومی) نیز اضافه و
> resolver آن (`apps.stores.resolution.resolve_store_for_admin_host`) نوشته
> شده — **اما هنوز به `staff_required` متصل نشده**؛ یعنی فعلاً همچنان
> هر Host که به یک Store معتبر resolve شود (از جمله یک `StoreDomain`
> عمومی) می‌تواند `/admin-portal/` همان Store را نشان دهد. جلوگیری کامل از
> نمایش پنل مدیریت روی دامنهٔ عمومی فروشگاه، کار آیندهٔ صریحاً مستندشده
> است (نگاه کنید به بخش «Known Limitations» گزارش Phase 1B).
> در همین PR یک نشتی واقعی و مستقل کشف و رفع شد: `apps.dashboard.services.dashboard_service`
> و `report_service` تمام آمار سفارش/فروش/مشتری صفحهٔ اصلی داشبورد و
> گزارش‌ها را بدون فیلتر `store` محاسبه می‌کردند (`Order` از زمان ADR-14
> فیلد `store` مستقیم دارد، اما این دو سرویس هرگز به‌روزرسانی نشده بودند) —
> یعنی آمار «فروش امروز»، «سفارشات جدید»، «مشتریان»، نمودار فروش، نمودار
> وضعیت سفارش‌ها، پرفروش‌ترین‌ها و تمام گزارش‌های حرفه‌ای، داده‌ی همهٔ
> Storeها را با هم جمع می‌زدند. هر دو سرویس اکنون `store` را صریح می‌گیرند
> و تست ایزولاسیون Cross-Store دارند.

---

# 11. وضعیت دامنه‌ها

## 11.1 Tenancy و IAM

### موجود و قابل اتکا

- Store model؛
- StoreDomain؛
- Host resolution؛
- Store context؛
- جداسازی Merchant Dashboard و Platform Admin؛
- foundation اولیه StoreMembership.

### ناقص

- invitation lifecycle؛
- membership acceptance؛
- owner transfer؛
- deactivate/remove member؛
- role-based authorization؛
- permission registry؛
- Store switching برای platform users؛
- audit کامل تغییر عضویت؛
- quota/plan enforcement.

### وضعیت

**Partial — اولویت بالا**

---

## 11.2 Catalog

### موجود و تثبیت‌شده

- Vendor؛
- Category؛
- Brand؛
- Product؛
- ProductVariant؛
- ProductImage؛
- Specification؛
- Review؛
- simple/variable product؛
- Store-scoped slug و SKU؛
- Product CRUD (شامل برند، بارکد/وزن/نیاز به ارسال، seo_title/seo_description)؛
- Variant management؛
- media lifecycle اولیه، شامل تصویر مختص تنوع (`ProductImage.variant`)؛
- product list pagination/sort/bulk actions (فعال/غیرفعال/پیش‌نویس/حذف/تغییر دسته‌بندی)؛
- storefront isolation؛
- dashboard isolation؛
- wishlist isolation؛
- pricing boundary پایه.

### ناقص نسبت به محصول هدف

- Attribute definition عمومی و no-code در سطح حرفه‌ای؛
- AttributeValue و Option registry مستقل؛
- multi-attribute variant matrix؛
- bulk product import/export؛
- tag management کامل؛
- SEO contract کامل؛
- inventory ledger؛
- stock reservation؛
- warehouse support؛
- bulk price/stock editor؛
- product audit history؛
- category tree UX حرفه‌ای؛
- duplicate/clone product؛
- configurable product type templates؛
- query/performance validation در PostgreSQL.

### وضعیت

**Core foundation implemented; professional catalog incomplete**

---

## 11.3 Customer

### موجود

- Customer account؛
- authentication؛
- OTP؛
- profile؛
- Address؛
- Wishlist؛
- guest cart merge.

### ناقص

- direct Store ownership؛
- phone uniqueness strategy per Store؛
- cross-domain customer identity policy؛
- customer consent؛
- marketing opt-in/opt-out؛
- customer segmentation؛
- customer notes/tags؛
- activity timeline؛
- address geography registry؛
- privacy/export/delete workflows؛
- StoreMembership-independent customer authorization.

### تصمیم موردنیاز

بین دو الگو باید ADR قطعی شود:

1. Customer کاملاً Store-scoped؛
2. Global Identity + StoreCustomerProfile.

تا زمان ADR، نباید uniqueness یا data migration بزرگ Customer انجام شود.

### وضعیت

**Partial — معماری مالکیت حل‌نشده**

> **الحاقیه (پس از PR — Order Boundary and Checkout Integrity، ۱۴۰۵/۰۵/۰۴):**
> این PR عمداً uniqueness یا مدل Customer را تغییر نداد (طبق تصمیم بالا).
> در عوض، دید داشبورد به مشتریان از طریق رابطه‌ی موجود `Order.store` محدود
> شد: `customers_admin_service.annotated_customers` فقط مشتریانی را نشان
> می‌دهد که حداقل یک Order در همان Store دارند، و `order_count`/
> `paid_total` هر مشتری فقط شامل سفارش‌های همان Store است — مشتری‌ای که از
> هر دو Store خرید کرده در هر دو داشبورد دیده می‌شود، اما با مجموع‌های
> کاملاً جداگانه. این یک راه‌حل موقت در سطح Query است، نه پاسخ به تصمیم
> معماریِ بالا؛ همان دو گزینه هنوز باز و منتظر ADR است.

---

## 11.4 Cart و Pricing

### موجود

- Cart و CartItem؛
- add/update/remove؛
- Coupon پایه؛
- cart totals؛
- explicit Store در pricing؛
- دفاع در برابر Product/Variant متعلق به Store دیگر؛
- mixed-store cart rejection در Order creation.

### ناقص

- direct Store ownership روی Cart؛
- Store-scoped session/cart key؛
- coupon ownership per Store؛
- abandoned cart lifecycle؛
- cart merge با کنترل Tenant کامل؛
- tax rules حرفه‌ای؛
- shipping quotation contract؛
- price snapshot رسمی؛
- promotion stacking policy؛
- concurrency behavior؛
- expiration/cleanup؛
- persistence strategy برای guest cart میان Domainها.

### وضعیت

**Partial — Tenant boundary دفاعی، Aggregate ownership ناقص**

---

## 11.5 Orders

### موجود

- Order و OrderItem؛
- checkout service؛
- order creation؛
- status change؛
- payment simulation؛
- OrderLine snapshot اولیه؛
- SMS eventهای مرتبط؛
- dashboard views پایه.

### ناقص

- direct Store ownership؛
- authoritative state machine؛
- transition service واحد؛
- order number per Store؛
- fulfillment workflow؛
- cancellation/refund؛
- invoice lifecycle؛
- immutable financial snapshot کامل؛
- status history actor/audit؛
- concurrency lock؛
- stock reservation/release؛
- manual order creation contract؛
- order export؛
- return/exchange؛
- fraud controls.

### وضعیت

**Partial — اولویت بسیار بالا**

> **الحاقیه (پس از PR — Order Boundary and Checkout Integrity، ۱۴۰۵/۰۵/۰۴):**
> موارد زیر از فهرست «ناقص» بالا اکنون پیاده‌سازی شده‌اند:
> **مالکیت مستقیم Store** (`Order.store`، FK مستقیم و اجباری، علاوه بر
> `vendor`؛ نگاه کنید به ADR-14 در `SAAS_DOMAIN_DECISIONS.md`)؛
> **قفل concurrency و رزرو موجودی** (`select_for_update` + کاهش شرطی
> موجودی درون تراکنش، در `order_service._lock_and_revalidate_items`)؛
> **اسنپ‌شات مالی کامل‌تر** (`OrderItem.sku`/`variant_label` اضافه شد)؛
> **audit تاریخچه‌ی وضعیت** (بدون تغییر مستقیم مجاز از Django Admin — نگاه
> کنید به بخش Admin پایین‌تر). هنوز ناتمام: order number مستقل به‌ازای هر
> Store (کد سفارش هنوز سراسری پلتفرم است، نه per-Store)، fulfillment
> workflow کامل، cancellation/refund رسمی، invoice lifecycle، export،
> return/exchange، fraud controls. **idempotency ثبت سفارش** با
> `Cart.checkout_token`/`Order.idempotency_key` پیاده‌سازی شد (ADR-15) —
> این یک قابلیت جدید بود که در فهرست اصلی «ناقص» بالا صراحتاً ذکر نشده
> بود اما به‌عنوان یک الزام امنیتی مجزا شناسایی و بسته شد.

---

## 11.6 Payment

### موجود

- PaymentGateway model/config اولیه؛
- Transaction؛
- simulation flow؛
- card/bank detection؛
- اتصال اولیه به Order.

### ناقص

- Store-owned gateway credentials؛
- encryption at rest؛
- adapter registry کامل؛
- request/verify callback واقعی؛
- idempotency key؛
- duplicate callback protection؛
- amount mismatch protection؛
- transaction state machine؛
- reconciliation؛
- refund؛
- payment audit؛
- production gateway tests؛
- secret rotation؛
- webhook security.

### وضعیت

**Prototype/Partial — برای Production آماده نیست**

> **الحاقیه (پس از PR — Order Boundary and Checkout Integrity، ۱۴۰۵/۰۵/۰۴):**
> `PaymentGateway` اکنون مالکیت مستقیم Store دارد (FK اجباری، یکتاییِ
> اسلاگ per-Store)؛ داشبورد فقط درگاه‌های همان Store را فهرست/toggle
> می‌کند و درخواست جعلی برای درگاه Store دیگر ۴۰۴ می‌گیرد. **این هنوز به
> معنای آماده‌بودن برای Production نیست** — درگاه پرداخت واقعی (Zibal)،
> اعتبارنامه‌ی رمزنگاری‌شده، callback واقعی، idempotency در سطح بانک،
> reconciliation و refund همچنان در فهرست «ناقص» بالا باقی می‌مانند و
> موضوع PR بعدی‌اند. جریان پرداخت فعلی همچنان صرفاً شبیه‌سازی‌شده است و
> اکنون به‌صراحت پشت `settings.PAYMENTS_SIMULATION_ENABLED` قرار دارد (که
> در استقرار واقعی با `DJANGO_DEBUG=False` به‌صورت پیش‌فرض غیرفعال است) —
> نه فقط مستنداً placeholder، بلکه واقعاً غیرقابل‌دسترس در Production.

---

## 11.7 Shipping

### موجود

- ShippingMethod پایه؛
- استفاده در checkout.

### ناقص

- Store ownership؛
- zone/region rules؛
- weight/price/free-shipping algorithms؛
- COD/postpaid policy؛
- delivery time estimates؛
- carrier adapters؛
- province/city restrictions؛
- per-product shipping restrictions؛
- shipment/fulfillment object؛
- tracking code؛
- partial shipment؛
- shipping audit.

### وضعیت

**Basic only**

> **الحاقیه (پس از PR — Order Boundary and Checkout Integrity، ۱۴۰۵/۰۵/۰۴):**
> `ShippingMethod` اکنون مالکیت مستقیم Store دارد (همان الگوی
> `PaymentGateway` بالا) — چک‌اوت فقط روش‌های ارسال فعالِ همان Store را
> می‌پذیرد و یک POST دستکاری‌شده نمی‌تواند روش ارسال Store دیگر را انتخاب
> کند. zone/region rules، carrier adapters، partial shipment و بقیه‌ی
> فهرست «ناقص» بالا همچنان پابرجاست.

---

## 11.8 Content، Navigation و Homepage

### موجود

- ContentPage؛
- HeroSlide؛
- PromotionalBanner؛
- SocialLink؛
- Menu و MenuItem؛
- Footer settings؛
- trust badges؛
- payment logos؛
- destination resolution؛
- dashboard management pages؛
- homepage configurability اولیه.

### نقص مهم تأییدشده

برخی destination relationها و Category selectorهای Hero، Banner و Menu هنوز Store-scoped نیستند.

این شکاف می‌تواند باعث شود یک Store در Content خود به Category یا Product Store دیگر اشاره کند.

### ناقص نسبت به Target

- Store ownership کامل؛
- draft/publish؛
- versioning؛
- page builder schema؛
- section registry؛
- preview؛
- rollback؛
- scheduling؛
- reusable blocks؛
- theme version؛
- page-level SEO؛
- audit؛
- safe custom HTML policy؛
- localization؛
- media isolation کامل.

### وضعیت

**Feature-rich UI foundation; tenant integrity incomplete**

---

## 11.9 Theme و Appearance

### موجود

- logo؛
- favicon؛
- primary/accent color؛
- color validation؛
- contrast calculation؛
- theme presets؛
- CSS tokens؛
- footer appearance؛
- theme-independent admin shell direction.

### ناقص

- versioned draft/publish theme؛
- visual section editor؛
- theme package registry؛
- font management؛
- per-page layout؛
- preview token؛
- safe custom CSS policy؛
- rollback؛
- theme migration/version compatibility؛
- Store-specific asset namespaces کامل.

### اصل غیرقابل‌تغییر

Theme نباید Business Logic، Route، Permission، ViewModel یا Workflow را تغییر دهد.

معماری UI:

```text
Design Tokens → Layout → Components → Pages
```

Storefront theme و Merchant Admin theme باید مستقل باشند.

### وضعیت

**Strong foundation; visual builder absent**

---

## 11.10 SMS و Notification

### موجود

- SmsTemplate؛
- SmsLog؛
- OtpCode؛
- Event enum؛
- provider backend؛
- explicit Store context؛
- OTP flow؛
- send test؛
- failure swallowing در boundary مناسب.

### ناقص

- Store ownership همه Template/Logها؛
- encrypted credentials؛
- provider abstraction حرفه‌ای؛
- async outbox؛
- retries؛
- delivery status callback؛
- rate limit؛
- consent؛
- suppression list؛
- idempotency؛
- cost reporting؛
- template variable validation کامل؛
- platform default vs Store override policy.

### وضعیت

**Partial**

---

## 11.11 Discounts و Campaigns

### موجود

- Coupon پایه؛
- بخشی از pricing application.

### ناقص

- Store ownership؛
- campaign؛
- usage limits؛
- customer eligibility؛
- product/category conditions؛
- stacking؛
- schedule؛
- minimum cart؛
- first-order؛
- audit؛
- redemption ledger؛
- race-condition-safe usage count؛
- SMS campaign؛
- consent filters؛
- performance metrics.

### وضعیت

**Mostly absent beyond basic coupon**

---

## 11.12 Reporting و Audit

### موجود

- Dashboard stat cards؛
- SVG charts؛
- report serviceهای اولیه؛
- recent orders/products؛
- برخی آمار فروش.

### ناقص

- authoritative reporting definitions؛
- per-Store metric contracts؛
- financial reports؛
- export jobs؛
- large dataset pagination؛
- date/timezone policy؛
- audit log عمومی؛
- actor/IP/user-agent؛
- before/after values؛
- report permissions؛
- scheduled reports؛
- immutable activity ledger.

### وضعیت

**Basic UI reports; platform-grade reporting absent**

---

## 11.13 SaaS Billing و Platform Operations

### تقریباً غایب

هدف آینده شامل:

- Plan؛
- Subscription؛
- Feature entitlement؛
- quotas؛
- trial؛
- invoice؛
- payment collection؛
- suspension/grace period؛
- usage metering؛
- domain management؛
- platform dashboard؛
- support access؛
- impersonation با audit؛
- tenant lifecycle؛
- backup/export/delete.

### وضعیت

**Absent — نباید قبل از بسته‌شدن domain ownershipهای اصلی آغاز شود**

---

# 12. تطبیق قابلیت‌های MixIn با پروژه

## 12.1 نقش خروجی‌های MixIn

خروجی‌های استخراج‌شده از صفحات MixIn برای موارد زیر ارزشمندند:

- Information Architecture؛
- منوی پنل؛
- ترتیب فرم‌ها؛
- Data table pattern؛
- onboarding؛
- report filters؛
- product editor؛
- order workflow UX؛
- appearance settings؛
- visual page builder؛
- campaign and SMS UX؛
- responsive behavior؛
- Persian/RTL expectations.

اما این موارد نباید عیناً کپی شوند:

- URLها؛
- نام Appها؛
- نام Modelها؛
- Schema؛
- تکنولوژی‌های فرضی؛
- permission model؛
- HTML/CSS مالکیتی؛
- branding یا assetهای اختصاصی.

## 12.2 Mapping مسیرها

| قابلیت MixIn | مسیر مرجع | مسیر/حوزه پروژه |
|---|---|---|
| Dashboard | `/admin/` | `/admin-panel/` |
| Products | `/admin/all-products/` | Dashboard catalog routes موجود |
| Create Product | `/admin/product-v3/create/` | Product create/edit موجود |
| Appearance | `/admin/appearance-settings/` | settings/appearance موجود |
| Theme Editor | `/admin/appearance-settings-v2/theme-edit/` | هنوز کامل نیست |
| Orders | `/admin/all-orders/` | Dashboard order routes موجود |
| Customers | `/admin/customers/` | Dashboard customer routes اولیه |
| Reports | `/admin/*-report/` | report services پایه |
| SMS | `/admin/sms-*` | dashboard SMS routes اولیه |
| Campaigns | `/admin/campaigns/` | عمدتاً غایب |

قاعده:

> UX capability منتقل شود؛ Route Contract کپی نشود.

---

# 13. Gap Matrix رسمی

| حوزه | وضعیت Repository | هدف | شکاف اصلی | اولویت |
|---|---|---|---|---|
| Store Resolution | Implemented | Domain-safe tenant resolution | lifecycle و custom-domain operations | بالا |
| Store Membership | Foundation | Role-based merchant IAM | authorization هنوز `is_staff` | بسیار بالا |
| Catalog | Core implemented | no-code professional catalog | attributes/import/inventory | بالا |
| Customer | Partial | Store-safe CRM | ownership policy | بسیار بالا |
| Cart | Partial | Store-owned cart | Store FK/session isolation | بسیار بالا |
| Order | Partial | stateful commerce engine | Store ownership/state machine | بسیار بالا |
| Payment | Prototype | secure gateway engine | idempotency/encryption/reconciliation | بسیار بالا |
| Shipping | Basic | rule-driven shipping | ownership/zones/fulfillment | بالا |
| Content | Rich partial | versioned CMS/page builder | cross-Store relations/draft-publish | بسیار بالا |
| Theme | Foundation | visual theme editor | versioning/preview/rollback | متوسط |
| SMS | Partial | reliable async messaging | outbox/retry/security | متوسط |
| Discount | Basic | promotion engine | eligibility/ledger/concurrency | متوسط |
| Reporting | Basic | audited per-Store analytics | definitions/export/permissions | متوسط |
| SaaS Billing | Absent | sellable platform | plan/subscription/quota | بعد از commerce core |
| Production | Not ready | secure operations | PostgreSQL/deploy/monitoring/backups | نهایی ولی ضروری |

---

# 14. ترتیب پیشنهادی توسعه از این نقطه

ترتیب زیر جایگزین اجرای کورکورانه Sprint Planهای مرجع است و بر اساس Repository فعلی تنظیم شده است.

## مرحله A — Repository/Product Reconciliation

خروجی:

- این سند در Repository؛
- Mapping رسمی اسناد مرجع؛
- active/deferred/obsolete docs classification؛
- Current Implementation Matrix؛
- ADR list؛
- Next Task رسمی.

هیچ Feature بزرگ در این مرحله ساخته نشود.

## مرحله B — Content Tenant Boundary

دلیل اولویت:

- نقص Cross-Store واقعی در Hero/Banner/Menu relationها تأیید شده؛
- Content اکنون UI قابل‌استفاده دارد ولی boundary آن ضعیف‌تر از Catalog است.

دامنه:

- ContentPage؛
- HeroSlide؛
- PromotionalBanner؛
- Menu/MenuItem؛
- Footer؛
- SocialLink؛
- BlogPost؛
- destination fields؛
- forms/querysets/media/context processors.

## مرحله C — Customer Ownership Decision

ابتدا ADR:

- Store-scoped Customer؛ یا
- Global identity + Store profile.

سپس Migration و adversarial tests.

## مرحله D — Cart/Coupon Tenantization

- direct Store ownership؛
- session isolation؛
- coupon per Store؛
- guest merge boundary؛
- mixed-domain tests.

## مرحله E — Order/Payment/Shipping Boundary

- Order Store FK؛
- ShippingMethod Store FK؛
- PaymentGateway configuration ownership؛
- Order number uniqueness per Store؛
- status machine؛
- payment idempotency؛
- immutable snapshots.

## مرحله F — Merchant IAM

- StoreMembership activation؛
- permissions؛
- role-based decorators/services؛
- حذف وابستگی merchant authorization به `is_staff`.

## مرحله G — Inventory and Promotion Hardening

- reservations؛
- atomic decrement؛
- coupon usage ledger؛
- concurrency tests.

## مرحله H — Page Builder and Theme Versioning

تنها پس از تثبیت Content ownership.

## مرحله I — Messaging Hardening

- encrypted credentials؛
- outbox؛
- retries؛
- rate limit؛
- callbacks.

## مرحله J — SaaS Billing and Platform Operations

تنها زمانی که Tenant lifecycle و merchant commerce core پایدار باشد.

---

# 15. قواعد مالی و Order

## 15.1 اصل Snapshot

OrderItem نباید برای تاریخچه مالی به Product جاری وابسته باشد.

در زمان ثبت سفارش باید حداقل Snapshotهای زیر ذخیره شوند:

- product title؛
- variant title/attributes؛
- SKU؛
- unit base price؛
- unit discount؛
- unit final price؛
- quantity؛
- line total؛
- tax component؛
- shipping allocation در صورت نیاز؛
- currency/unit.

تغییر آینده Product نباید Order تاریخی را تغییر دهد.

## 15.2 ترتیب محاسبه

ترتیب دقیق باید در ADR/Service واحد تثبیت شود. الگوی پیشنهادی:

1. Resolve sellable item؛
2. Validate Store ownership؛
3. Validate purchasability؛
4. Resolve unit price؛
5. Calculate line subtotal؛
6. Apply item-level discount؛
7. Apply eligible cart discount؛
8. Calculate shipping؛
9. Calculate tax مطابق policy؛
10. Produce immutable totals؛
11. Compare payment amount with authoritative payable amount.

هیچ View یا Template نباید independently price محاسبه کند.

## 15.3 واحد پول

Repository باید یک قرارداد واحد داشته باشد:

- مبلغ ذخیره‌شده به ریال یا تومان؛
- تبدیل نمایش؛
- rounding؛
- gateway amount unit؛
- export/report unit.

تا زمان ADR، اضافه‌کردن محاسبات مالی جدید بدون بررسی واحد پول ممنوع است.

---

# 16. قواعد Inventory

حداقل قرارداد آینده:

```text
available = on_hand - reserved
```

در Checkout:

1. cart validation؛
2. atomic reservation؛
3. Order creation؛
4. payment initiation؛
5. payment success → commit/decrement policy؛
6. payment failure/timeout/cancel → release reservation.

ضروری:

- transaction.atomic؛
- row locking یا atomic conditional update؛
- جلوگیری از oversell؛
- idempotent release؛
- audit movement؛
- مدیریت simple و variable product یکسان.

تا پیش از ساخت Inventory Ledger، فیلدهای فعلی stock باید به‌عنوان راه‌حل محدود مستند شوند.

---

# 17. قواعد Payment

هر Gateway باید Adapter contract داشته باشد:

```text
create_payment(order, amount, callback_url)
verify_payment(reference, expected_amount)
refund_payment(transaction, amount)
```

حداقل invariantها:

- credentials Store-owned و encrypted؛
- callback idempotent؛
- duplicate callback بی‌اثر؛
- amount mismatch reject؛
- Order فقط از Transaction معتبر paid شود؛
- Transaction code/reference uniqueness درست؛
- status transition محدود؛
- raw provider response امن و redacted ذخیره شود؛
- timeout و retry تعریف شود؛
- refund مستقل از order cancellation مدل شود.

Payment simulation تنها ابزار توسعه است و نباید در Production به‌عنوان Gateway تلقی شود.

---

# 18. قواعد Content و Page Builder

## 18.1 Store boundary

هر Content aggregate باید مستقیم یا inherited به Store تعلق داشته باشد.

تمام relationها مانند:

- Product؛
- Category؛
- Brand؛
- BlogPost؛
- Page؛
- Menu parent؛
- Banner destination

باید از همان Store باشند.

Filtered dropdown کافی نیست؛ crafted POST باید server-side رد شود.

## 18.2 Draft/Publish

مدل هدف:

```text
Draft Version
    ├── editable config
    ├── previewable
    └── not public

Published Version
    ├── immutable snapshot
    ├── currently active
    └── rollback target
```

هر Publish باید atomic باشد و امکان Rollback داشته باشد.

## 18.3 Section Registry

Page builder نباید Typeهای section را با if/else پراکنده در Template مدیریت کند.

Registry هدف باید برای هر Section type تعریف کند:

- schema؛
- validation؛
- renderer؛
- default config؛
- editor component؛
- version compatibility؛
- allowed destinations؛
- caching behavior.

Custom HTML باید محدود، sanitize یا فقط برای Platform-trusted users باشد.

---

# 19. امنیت

## 19.1 Tenant security

- هر Query merchant data باید Store-scoped باشد؛
- Object ID از client هرگز ownership را اثبات نمی‌کند؛
- relation fields باید Store-scoped باشند؛
- Bulk operations باید Store filter اجباری داشته باشند؛
- exports باید Store identity را حفظ کنند؛
- filenames/storage paths به‌تنهایی authorization نیستند؛
- logs نباید secrets یا OTP را افشا کنند.

## 19.2 File upload

الزامات:

- content validation، نه فقط extension؛
- size limits؛
- image decode/verify؛
- منع SVG/HTML ناامن؛
- random/stable paths؛
- Store namespace؛
- safe replacement؛
- physical cleanup after commit؛
- عدم حذف فایل Store دیگر؛
- object storage compatibility.

## 19.3 Secrets

ممنوع:

- Secret key Production در Repository؛
- gateway/SMS credential plaintext؛
- credential نمایش کامل در Dashboard؛
- log کردن token یا password؛
- استفاده از DEBUG در Production.

---

# 20. Cache، Session، Media و Job

هر key یا durable task باید Store identity داشته باشد.

## Cache key

```text
store:{store_id}:catalog:{...}
store:{store_id}:settings:{...}
```

## Session

Guest cart نباید میان Domainهای متفاوت leak شود.

## Media

پیشنهاد path:

```text
stores/{store_id}/catalog/products/{product_id}/...
stores/{store_id}/content/...
stores/{store_id}/branding/...
```

Path جای Authorization را نمی‌گیرد.

## Background Job

هر Job باید شامل durable Store ID باشد و هنگام اجرا:

- Store را دوباره validate کند؛
- از Request یا Thread-local استفاده نکند؛
- idempotency داشته باشد؛
- status و error logging داشته باشد.

---

# 21. PostgreSQL و Production

SQLite برای توسعه و تست فعلی پذیرفته است، اما معیار نهایی Production نیست.

پیش از عرضه:

- PostgreSQL؛
- تست Migration واقعی؛
- constraint behavior؛
- select_for_update؛
- partial index؛
- query plan؛
- timezone؛
- backup/restore؛
- connection pooling؛
- object storage؛
- secure headers؛
- CSRF/session/cookie settings؛
- logging/monitoring؛
- error reporting؛
- health checks؛
- CI/CD؛
- rollback deployment.

هر قابلیت concurrency-sensitive باید حداقل یک بار روی PostgreSQL تست شود.

> **الحاقیه (پس از PR — Production Configuration Foundation، ۱۴۰۵/۰۵/۰۴):**
> موارد زیر از فهرست بالا اکنون از طریق environment variable قابل‌پیکربندی
> شده‌اند (پیش‌فرض توسعه/تست بدون تغییر باقی مانده است):
> `DJANGO_SECRET_KEY`، `DJANGO_DEBUG`، `DJANGO_ALLOWED_HOSTS`،
> `DJANGO_CSRF_TRUSTED_ORIGINS`، تنظیمات HTTPS/secure-cookie/HSTS،
> `DATABASE_URL` (PostgreSQL از طریق `psycopg`)، `DJANGO_STATIC_ROOT`،
> `DJANGO_MEDIA_ROOT`، و یک پیکربندی `LOGGING` حداقلی. جزئیات کامل و راهنمای
> استقرار در `docs/deployment/PRODUCTION_CONFIGURATION.md` و
> `.env.example` است. **این تغییر پایه‌ی پیکربندی است، نه آمادگی کامل
> Production** — موارد زیر همچنان ناتمام‌اند: انتقال واقعی به PostgreSQL در
> یک محیط واقعی، select_for_update/inventory locking، backup/restore
> تست‌شده، CI/CD، health checks عملیاتی، و انتخاب ارائه‌دهنده‌ی هاست.

> **الحاقیه ۲ (پس از PR — Order Boundary and Checkout Integrity، ۱۴۰۵/۰۵/۰۴):**
> `select_for_update()` اکنون در `order_service._lock_and_revalidate_items`
> پیاده‌سازی شده — روی ردیف‌های Product/ProductVariant، به ترتیب پایدار
> بر اساس pk (کاهش ریسک deadlock)، پیش از بازاعتبارسنجی موجودی/وضعیت/مالکیت
> Store. **این هنوز به معنای اثبات‌شده‌بودن رفتار concurrency روی Production
> نیست** — SQLite (که کل تست‌ها روی آن اجرا می‌شوند) به‌جای قفل واقعیِ سطح
> ردیف، کل دیتابیس را هنگام نوشتن قفل می‌کند؛ یعنی دو تراکنشِ «هم‌زمان» روی
> SQLite در عمل به‌صورت متوالی اجرا می‌شوند، نه واقعاً هم‌زمان. تست
> `apps/orders/tests/test_checkout_correctness.py::CheckoutIdempotencyServiceTests.test_concurrent_race_simulated_via_preexisting_conflicting_order`
> مسیر race را به‌صورت قطعی (نه با thread واقعی) شبیه‌سازی می‌کند تا کد
> واقعی catch/refetch را تست کند، اما این جایگزین تست واقعی روی PostgreSQL
> تحت بار هم‌زمان واقعی نیست — همچنان در فهرست تأییدهای پیش از عرضه باقی
> می‌ماند.

---

# 22. تست اجباری

هر Tenant-sensitive PR باید حداقل دو Store و دو Domain واقعی داشته باشد.

## 22.1 الگوی تست

```text
Store A + verified Domain A
Store B + verified Domain B
Object A owned by Store A
Object B owned by Store B
User A authorized for Store A
User B authorized for Store B
```

## 22.2 گروه‌های اجباری

- Host A فقط داده A؛
- Host B فقط داده B؛
- PK و slug cross-Store → 404؛
- crafted POST relation → reject؛
- denied mutation → DB unchanged؛
- bulk update/delete scoped؛
- unknown Host fail-closed؛
- inactive Store denied؛
- management command Store explicit؛
- migration zero/one/multiple owner scenarios؛
- forward/rollback/forward؛
- cache/session keys isolated؛
- physical media lifecycle؛
- payment callback idempotency؛
- concurrency tests برای stock/coupon/payment.

## 22.3 ممنوعیت تضعیف تست

ممنوع:

- status range گسترده بدون دلیل؛
- حذف assertion وضعیت DB؛
- mock کردن همه Store resolutionها؛
- skip کردن تست امنیتی؛
- تغییر expected failure برای سبزکردن suite؛
- شمارش کل suite به‌عنوان «تست جدید».

---

# 23. قواعد Migration

Migrationهای Tenantization باید staged باشند:

1. nullable field/structure؛
2. deterministic backfill؛
3. validation؛
4. constraints/indexes؛
5. non-null enforcement.

قواعد:

- فقط `apps.get_model`؛
- بدون import runtime model؛
- بدون `.first()`؛
- بدون `pk=1`؛
- بدون silent assignment مبهم؛
- failure بلند و واضح؛
- حفظ ID و merchant data؛
- reverse policy مستند؛
- تست forward/rollback/forward.

Akhlaghi فقط زمانی backfill owner معتبر است که تاریخچه Repository ثابت کند داده پیش از Tenant فقط متعلق به همان فروشگاه بوده است.

---

# 24. قواعد UI/UX

## 24.1 اصول

- فارسی و RTL واقعی؛
- mobile-first؛
- accessibility؛
- keyboard navigation؛
- focus state؛
- empty/loading/error/success states؛
- optimistic behavior فقط با rollback معتبر؛
- ارقام و تاریخ مطابق قرارداد؛
- status badgeهای ثابت؛
- confirmation برای عملیات مخرب؛
- حفظ filter/search/pagination state؛
- HTMX partialها با fallback کامل.

## 24.2 Data Table Contract

هر جدول حرفه‌ای باید در صورت نیاز دارای:

- search؛
- filter؛
- sort؛
- pagination؛
- bulk selection؛
- explicit bulk authorization؛
- empty state؛
- export async برای داده حجیم؛
- responsive mobile representation.

## 24.3 Product Editor

قرارداد هدف:

- Simple/Variable انتخاب روشن؛
- اطلاعات پایه؛
- media؛
- category/brand؛
- pricing؛
- inventory؛
- shipping؛
- specifications؛
- SEO؛
- publication؛
- variant matrix؛
- validation summary؛
- save draft/publish؛
- unsaved-change warning.

پیاده‌سازی باید تدریجی باشد و منطق Variant موجود حفظ شود.

---

# 25. Definition of Done

یک قابلیت فقط زمانی Done است که:

1. مدل و ownership روشن است؛
2. Service contract دارد؛
3. Authorization server-side دارد؛
4. Store isolation دارد؛
5. happy path تست شده؛
6. adversarial path تست شده؛
7. migration تست شده؛
8. UI states کامل است؛
9. audit/logging مناسب دارد؛
10. docs و ADR sync شده‌اند؛
11. full regression سبز است؛
12. open PR wording دقیق است؛
13. هیچ test یا security assertion تضعیف نشده؛
14. no migration drift؛
15. rollback یا recovery مشخص است.

---

# 26. Workflow الزامی هر PR

## قبل از تغییر

- checkout branch درست؛
- fetch/pull؛
- clean tree؛
- HEAD SHA؛
- baseline check؛
- migration drift؛
- focused tests؛
- full architecture inventory.

## حین تغییر

- کمترین Scope؛
- بدون refactor نامرتبط؛
- بدون redesign پنهان؛
- source of Store ثبت شود؛
- production callers inventory؛
- negative tests؛
- docs همزمان.

## قبل از Commit

```text
git status --short
git diff --stat
git diff --name-status
git diff
git diff --check
```

## Validation

- `manage.py check`
- `makemigrations --check --dry-run`
- focused suites
- affected app suites
- full suite
- migration cycle در صورت Schema change

## Pull Request

- یک Branch؛
- یک PR؛
- target branch رسمی؛
- عدم Merge توسط Agent؛
- exact test counts؛
- known limitations؛
- open/merged wording صحیح.

---

# 27. اسناد Repository پیشنهادی

ساختار پیشنهادی:

```text
docs/
├── 00_PROJECT_MASTER_REFERENCE.md        ← همین سند
├── 01_PROJECT_RULES.md
├── 02_CURRENT_IMPLEMENTATION.md
├── 03_NEXT_TASK.md
├── architecture/
│   ├── SAAS_ARCHITECTURE.md
│   ├── SAAS_DOMAIN_DECISIONS.md
│   ├── SAAS_MIGRATION_PLAN.md
│   └── OWNERSHIP_MATRIX.md
├── product/
│   ├── TARGET_CAPABILITY_MAP.md
│   ├── ADMIN_INFORMATION_ARCHITECTURE.md
│   ├── STOREFRONT_AND_THEME_TARGET.md
│   └── REPOSITORY_TARGET_GAP_MATRIX.md
├── quality/
│   ├── TEST_STRATEGY.md
│   ├── SECURITY_BOUNDARIES.md
│   └── PRODUCTION_READINESS.md
└── archive/
    └── extracted-reference-reports/
```

اسناد MixIn و خروجی‌های AI باید در `archive` یا `references` قرار گیرند و برچسب زیر داشته باشند:

> Reference-only — not source of truth.

---

# 28. تصمیم‌های قطعی

1. محصول Multi-tenant Store Builder است.
2. Store مرز Tenant است؛ Vendor نیست.
3. Akhlaghi اولین Tenant است؛ fallback عمومی نیست.
4. Shared database + row-level Store isolation معماری فعلی است.
5. Host/StoreDomain منبع Store در HTTP است.
6. Store باید در boundary resolve و صریحاً منتقل شود.
7. همه Childها direct Store FK نمی‌گیرند.
8. Merchant Dashboard و Platform Admin جدا هستند.
9. Django Admin فقط Platform Superuser است.
10. Storefront و Admin theme-independent باقی می‌مانند.
11. Modular Monolith حفظ می‌شود.
12. Repository بر HTML و گزارش مرجع اولویت دارد.
13. Cart، Order، Customer و Content هنوز Tenantization کامل ندارند.
14. PostgreSQL هدف Production است.
15. UI بدون Domain invariant معتبر Done نیست.

---

# 29. تصمیم‌های باز

موارد زیر نیازمند ADR مستقل‌اند:

- Customer identity model؛
- Cart ownership و session strategy؛
- Order code generation per Store؛
- Money unit؛
- tax ordering؛
- inventory reservation model؛
- payment adapter contract؛
- content versioning؛
- page builder schema؛
- theme package/versioning؛
- StoreMembership roles؛
- platform plans/quotas؛
- async outbox timing؛
- search architecture؛
- media object storage؛
- audit retention؛
- deletion/export policy.

تا زمان ADR، هیچ تصمیم بزرگ Schema در این حوزه‌ها نباید صرفاً از گزارش MixIn کپی شود.

---

# 30. ریسک‌های اصلی فعلی

## بحرانی

- Content cross-Store relation؛
- Customer ownership مبهم؛
- Cart و Order بدون direct Store ownership؛
- Payment غیرProduction؛
- merchant IAM وابسته به `is_staff`.

## بالا

- inventory concurrency؛
- coupon usage concurrency؛
- SMS credential/security؛
- media namespace؛
- Order state machine؛
- payment callback idempotency؛
- global uniquenessهای باقی‌مانده؛
- context processorهای Storeless احتمالی.

## متوسط

- reporting definitions؛
- theme versioning؛
- import/export؛
- cache key design؛
- audit coverage؛
- PostgreSQL performance.

---

# 31. کار بعدی پیشنهادی

## عنوان

**Content, Navigation and Homepage Tenant Boundary Assessment**

## دلیل

این حوزه هم‌اکنون:

- Featureهای واقعی و UI فعال دارد؛
- به Catalog relation دارد؛
- شکاف Cross-Store تأییدشده دارد؛
- پیش‌نیاز Page Builder و Theme Editor است.

## Scope پیشنهادی

- ContentPage؛
- HeroSlide؛
- PromotionalBanner؛
- SocialLink؛
- Menu؛
- MenuItem؛
- FooterSettings و children؛
- BlogPost؛
- destination relations؛
- dashboard forms؛
- context processors؛
- media؛
- storefront rendering؛
- two-Store/Host tests؛
- staged migrations فقط در صورت نقص اثبات‌شده.

## خارج از Scope

- visual page builder؛
- theme redesign؛
- rich editor جدید؛
- SaaS Billing؛
- Campaign؛
- Redis/Celery؛
- full IAM redesign.

---

# 32. دستور شروع برای عامل جدید

هر عامل جدید باید:

1. این سند را بخواند؛
2. active ADRها را بخواند؛
3. HEAD و test baseline را تأیید کند؛
4. Repository را source of truth بداند؛
5. هیچ ساختار فایل یا Model را از این سند فرض نکند؛
6. ابتدا inventory واقعی تولید کند؛
7. مغایرت سند و کد را گزارش دهد؛
8. فقط پس از تأیید، تغییر محدود ایجاد کند؛
9. Merge انجام ندهد؛
10. مستندات را با وضعیت PR همگام کند.

پرامپت کوتاه استاندارد:

```text
Read docs/00_PROJECT_MASTER_REFERENCE.md first.
Treat the current repository code, migrations, and tests as the ultimate source
of truth. Verify every assumption against the checked-out HEAD.

This is a multi-tenant store-builder SaaS platform. Akhlaghi is the first real
Store, not a global fallback. Store is the tenant boundary.

Do not implement from reference HTML or extracted MixIn reports directly.
Use them only as product and UX targets.

Before changing code, report the current branch, HEAD, clean status, migration
drift, test baseline, real model ownership graph, and all production access
paths affected by the task.

Challenge any requested change that weakens tenant isolation, authorization,
financial integrity, concurrency, migration safety, test quality, or the
theme-independent architecture.
```

---

# 33. نتیجه اجرایی

پروژه از مرحله «فروشگاه تک‌مستاجره با قابلیت‌های زیاد» عبور کرده و وارد مرحله «تثبیت یک پلتفرم فروشگاه‌ساز واقعی» شده است.

تا پایان PR #21:

- Tenant foundation وجود دارد؛
- Store settings ایزوله شده‌اند؛
- Store context در Pricing/SMS صریح شده؛
- Catalog tenant boundary تثبیت شده؛
- Django Admin از Merchant Dashboard جدا شده؛
- تست adversarial قابل توجه وجود دارد.

اما محصول هنوز برای فروش عمومی یا Production کامل آماده نیست. مهم‌ترین مسیر ادامه:

```text
Content Boundary
→ Customer Ownership
→ Cart Tenantization
→ Order/Payment/Shipping Integrity
→ Merchant IAM
→ Inventory/Promotion Concurrency
→ Page Builder/Theme Versioning
→ Messaging Hardening
→ SaaS Billing
→ Production Readiness
```

این سند باید پس از هر فاز بزرگ به‌روزرسانی شود، اما تاریخچه تصمیم‌ها نباید بازنویسی شود. تغییر تصمیم معماری باید از طریق ADR جدید یا Addendum ثبت شود.

---

# پیوست A — چک‌لیست سریع بازبین

- [ ] Store source authoritative است؟
- [ ] Query root Store-scoped است؟
- [ ] relation IDs از همان Store هستند؟
- [ ] crafted POST رد می‌شود؟
- [ ] bulk action scoped است؟
- [ ] denied operation DB را تغییر نمی‌دهد؟
- [ ] Child direct Store FK واقعاً لازم است؟
- [ ] uniqueness per Store درست است؟
- [ ] cache/session/media/job Store identity دارد؟
- [ ] money snapshot معتبر است؟
- [ ] transition/idempotency/concurrency بررسی شده؟
- [ ] migration deterministic و reversible است؟
- [ ] tests دو Store/Domain واقعی دارند؟
- [ ] docs وضعیت open/merged را درست می‌گویند؟
- [ ] UI reference بدون کپی معماری استفاده شده؟
- [ ] full regression سبز است؟

---

# پیوست B — وضعیت خلاصه قابلیت‌ها

| Capability | Status |
|---|---|
| Store/Domain foundation | Implemented |
| Core settings scoping | Implemented |
| Explicit service Store context | Implemented |
| Catalog tenant boundary | Implemented |
| Product variations | Implemented foundation |
| Merchant Dashboard | Implemented foundation |
| Platform Admin separation | Implemented |
| Content management | Partial |
| Theme/appearance | Partial |
| Customer | Partial |
| Cart | Partial |
| Orders | Partial — direct Store ownership + concurrency locking + checkout idempotency implemented; order-number-per-Store, fulfillment/refund/invoice-lifecycle still pending |
| Payment | Prototype/Partial — Store-owned PaymentGateway; simulation now gated off in production (`PAYMENTS_SIMULATION_ENABLED`); real gateway (Zibal) still pending |
| Shipping | Basic — Store-owned ShippingMethod; zone/carrier/fulfillment still pending |
| SMS | Partial |
| Discounts | Basic |
| Reporting | Basic |
| Inventory engine | Absent/Basic fields only |
| Page builder | Absent |
| Merchant RBAC | Absent/Foundational model only |
| SaaS billing | Absent |
| Production hardening | Partial — configuration foundation (env-driven settings, PostgreSQL-capable DB, logging) AND Order/dashboard Store boundary AND checkout idempotency/inventory-locking now implemented; PostgreSQL deployment against a real instance, Zibal, Enamad, backups, and hosting selection still pending |

---

# پیوست C — برچسب وضعیت اسناد

هر سند Repository باید یکی از وضعیت‌های زیر را در ابتدای خود داشته باشد:

```text
ACTIVE — authoritative and maintained
REFERENCE — target/UX reference only
HISTORICAL — accurate for a past state
SUPERSEDED — replaced by a newer document
DRAFT — not approved for implementation
```

این سند:

```text
ACTIVE
```
