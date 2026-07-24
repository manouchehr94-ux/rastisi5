# apps.content — مدیریت محتوای فروشگاه

## مسئولیت

این اپلیکیشن مسئول زیرساخت محتوای مدیریت‌شده‌ی فروشگاه است:
- مقصدهای امن (Safe Destination)
- صفحات محتوایی (ContentPage)
- لینک‌های شبکه‌های اجتماعی (SocialLink)
- بخش‌های صفحه اصلی (HeroSlide, PromotionalBanner)
- منوهای ناوبری (آینده)

## صفحات محتوایی (ContentPage)

### مالکیت و URL
- مدل: `apps.content.models.ContentPage`
- URL فروشگاه: `/pages/<slug>/`
- داشبورد: `/admin-panel/pages/`

### وضعیت انتشار
- `draft`: پیش‌نویس — فقط در داشبورد قابل مشاهده
- `published`: منتشرشده — عمومی قابل مشاهده

### قوانین:
- صفحات پیش‌نویس: 404 برای کاربران عادی
- انتشار: `published_at` و `published_by` ثبت می‌شود
- برگشت به پیش‌نویس: `published_at` و `published_by` پاک می‌شود
- قید دیتابیسی: `status=published` الزاماً `published_at IS NOT NULL`

### رندر متن
- متن صفحه **plain text** است (بدون HTML)
- رندر با `linebreaksbr` (خط‌شکن‌ها حفظ، HTML اسکیپ)
- هیچ `|safe` یا `mark_safe` استفاده نمی‌شود
- محتوای `<script>` و سایر HTML خطرناک اسکیپ می‌شود

### SEO
- `seo_title`: اگر خالی → fallback به `title`
- `seo_description`: اگر خالی → بدون متا تگ
- متا تگ `<meta name="description">` فقط وقتی توضیحات موجود رندر می‌شود

### فوتر
- `show_in_footer`: نمایش/عدم نمایش در فوتر
- `footer_column`: ستون (دسترسی سریع / خدمات مشتریان)
- فقط صفحات `published` در فوتر نمایش داده می‌شوند
- URL واقعی (`get_absolute_url`) — هرگز `href="#"`

### سطح دسترسی
- داشبورد: `@staff_required`
- عملیات مخرب (حذف/انتشار): فقط POST

### محدودیت `full_clean()`
- `save()` و `objects.create()` در Django به‌صورت خودکار `full_clean()` را صدا نمی‌زنند
- مسیر تولیدی (داشبورد): `full_clean()` قبل از `save()` صدا زده می‌شود
- ایجاد مستقیم ORM: ممکن است بدون اعتبارسنجی اجرا شود
- قید دیتابیسی `content_page_published_requires_timestamp` این را تا حدی پوشش می‌دهد

## معماری مقصد امن

### نوع‌های مقصد (DestinationType)

| نوع | توضیح |
|-----|-------|
| `none` | بدون لینک |
| `category` | لینک به دسته‌بندی (FK) |
| `product` | لینک به محصول (FK) |
| `brand` | لینک به برند (FK) |
| `external` | لینک خارجی (URL اعتبارسنجی‌شده) |

### قوانین اعتبارسنجی

- هر رکورد دقیقاً **یک** مقصد مطابق نوع انتخاب‌شده دارد
- ترکیب چند مقصد ممنوع است
- URL خارجی فقط طرح‌های `https`, `http`, `mailto`, `tel` را می‌پذیرد
- `javascript:`, `data:`, `vbscript:`, `//...` رد می‌شوند
- اعتبارسنجی در سطح مدل (`clean()`) انجام می‌شود

### رفتار حذف (Deletion)

- تمام FK‌ها: `on_delete=SET_NULL`
- حذف مقصد → resolver بازمی‌گرداند `None`
- هرگز `#` برنمی‌گرداند

### تصمیمات معماری

| تصمیم | دلیل |
|-------|------|
| عدم استفاده از `GenericForeignKey` | عدم ایمنی ارجاعی، عدم پشتیبانی از JOIN |
| عدم ذخیره مسیر خام داخلی | شکنندگی URL هنگام تغییر مسیرها |
| عدم پیاده‌سازی HomepageLayout در این PR | جلوگیری از تعمیم زودهنگام |
| عدم پیاده‌سازی PublishableModel | تفاوت معنایی انتشار بین ContentPage و HomepageLayout |
| عدم ویرایشگر ریچ‌تکست | نیاز به تصمیم جداگانه درباره سنیتایزر (nh3/bleach) |

### مصرف‌کنندگان مقصد امن

- `HeroSlide` (اسلایدر صفحه اصلی) — **پیاده‌شده در PR #8**
- `PromotionalBanner` (بنرهای تبلیغاتی) — **پیاده‌شده در PR #8**
- `MenuItem` (ناوبری هدر/فوتر) — آینده
- `HomepageSection` (دکمه‌های CTA) — آینده
- `ContentPage` (پس از اضافه شدن، نوع مقصد جدیدی اضافه می‌شود) — آینده

---

## مدیریت صفحه اصلی (Homepage Media — PR #8)

### بررسی کلی

اسلایدهای اصلی (HeroSlide) و بنرهای تبلیغاتی (PromotionalBanner) از طریق
داشبورد اختصاصی فروشگاه مدیریت می‌شوند. کاربر staff می‌تواند محتوای تبلیغاتی
صفحه اصلی را بدون تغییر کد یا دسترسی مستقیم به دیتابیس کنترل کند.

### دسترسی داشبورد

- مسیر: `/admin-panel/homepage/hero/` و `/admin-panel/homepage/banners/`
- سطح دسترسی: `@staff_required`
- ناوبری: از طریق سایدبار داشبورد → «مدیریت صفحه اصلی» → «اسلایدهای اصلی» / «بنرهای تبلیغاتی»

### عملیات پشتیبانی‌شده

| عملیات | HeroSlide | PromotionalBanner |
|--------|-----------|-------------------|
| ایجاد | ✅ | ✅ |
| ویرایش | ✅ | ✅ |
| حذف (فقط POST) | ✅ | ✅ |
| فعال/غیرفعال‌سازی (فقط POST) | ✅ | ✅ |
| ترتیب‌دهی عددی | ✅ | ✅ |

### فیلدهای فرم

هر دو مدل:
- عنوان (title)
- زیرعنوان/توضیحات (subtitle / description)
- تصویر دسکتاپ (الزامی)
- تصویر موبایل (اختیاری)
- نمایش دکمه (show_button)
- متن دکمه (button_label)
- نوع مقصد (destination_type)
- مقدار مقصد (FK یا URL)
- باز شدن در تب جدید (open_in_new_tab)
- وضعیت فعال (is_active)
- ترتیب نمایش (display_order)

### تصاویر

#### قوانین تصویر دسکتاپ
- **الزامی** در ایجاد
- در ویرایش، اگر فایل جدیدی آپلود نشود، تصویر فعلی حفظ می‌شود
- جایگزینی: فایل جدید ذخیره → فایل قبلی پس از commit حذف می‌شود
- حذف بدون جایگزین ممکن نیست

#### قوانین تصویر موبایل
- **اختیاری**
- در ویرایش، اگر تغییری نباشد، حفظ می‌شود
- قابل جایگزینی
- قابل حذف صریح (checkbox «حذف تصویر موبایل»)
- اگر هم‌زمان جایگزین و حذف ارسال شود، **جایگزینی اولویت دارد**
- حذف → فایل قبلی پس از commit حذف می‌شود

#### حداکثر حجم آپلود
- **۵ مگابایت (5 MiB)** برای هر فایل تصویر
- اعمال بر: desktop_image و mobile_image هر دو مدل
- اعتبارسنجی: **سمت سرور** (validator روی فیلد مدل)
- تصویر بزرگ‌تر از حد مجاز: خطای اعتبارسنجی — تصویر فعلی بدون تغییر باقی می‌ماند
- بدون پیش‌نمایش حجم سمت کلاینت

### چرخه‌ی زندگی فایل (File Lifecycle)

تمام حذف فایل‌ها از طریق `transaction.on_commit()` انجام می‌شود:

| سناریو | رفتار |
|---------|-------|
| جایگزینی تصویر (ویرایش موفق) | فایل قبلی پس از commit DB حذف می‌شود |
| حذف تصویر موبایل (ویرایش موفق) | فایل قبلی پس از commit DB حذف می‌شود |
| حذف مدل (delete) | فایل‌های desktop و mobile پس از commit حذف می‌شوند |
| شکست اعتبارسنجی (full_clean) | **هیچ فایلی حذف نمی‌شود** — تصاویر فعلی دست‌نخورده |
| شکست ذخیره‌سازی DB | **هیچ فایلی حذف نمی‌شود** |

- از Django Storage API استفاده می‌شود
- هیچ فرض filesystem محلی وجود ندارد
- فایل‌های یتیم (orphan) در سناریوی خطای غیرمنتظره ممکن‌اند ولی حداقل‌اند

### وضعیت خالی صفحه اصلی (Empty State)

| شرایط | رفتار |
|--------|-------|
| هیچ HeroSlide فعالی وجود ندارد | بخش هیرو کاملاً حذف می‌شود (omitted) |
| هیچ PromotionalBanner فعالی وجود ندارد | بخش بنر کاملاً حذف می‌شود |
| همه غیرفعال شوند | **هیچ کمپین hardcoded قدیمی بازنمی‌گردد** |
| سایر بخش‌های صفحه اصلی | بدون تغییر باقی می‌مانند (محصولات، دسته‌ها، بلاگ) |

مدیر فروشگاه کنترل کامل بر محتوای نمایشی صفحه اصلی دارد.

### مقصدهای CTA

مقصدهای فعال در داشبورد:

| نوع مقصد | وضعیت |
|-----------|--------|
| `category` (دسته‌بندی) | ✅ فعال |
| `external` (لینک خارجی) | ✅ فعال |
| `product` (محصول) | ⏳ تأخیری — مدیریت محصول خارج از محدوده PR #8 |
| `brand` (برند) | ⏳ تأخیری — مدیریت محصول خارج از محدوده PR #8 |

#### رفتار CTA
- دکمه فقط وقتی رندر می‌شود که `show_button=True` **و** `button_label` معتبر **و** مقصد با موفقیت resolve شود
- هرگز anchor خالی (`<a href="#">`) تولید نمی‌شود
- `target="_blank"` همراه با `rel="noopener noreferrer"` است
- محتوای عنوان/توضیحات توسط Django auto-escape محافظت می‌شود

### ترتیب نمایش (Ordering)

- فیلد عددی `display_order` (PositiveIntegerField)
- ترتیب اول: `display_order` صعودی
- Tiebreaker: `id` صعودی
- بدون قابلیت drag-and-drop (ترتیب عددی دستی)

### بهینه‌سازی Query

- یک query برای HeroSlide‌های فعال
- یک query برای PromotionalBanner‌های فعال
- بدون N+1 روی مقصدها (resolve در template tag بدون DB hit اضافه برای FK‌های loaded)
- بدون استفاده از context processor سراسری

### محدودیت‌های شناخته‌شده

- drag-and-drop ordering پیاده‌سازی نشده (عددی دستی)
- پیش‌نمایش حجم فایل سمت کلاینت وجود ندارد
- مقصد product/brand در UI داشبورد فعلاً پنهان (مدل آماده)
- تأیید حذف (confirmation dialog) پیاده‌سازی نشده
- بهینه‌سازی تصویر (resize/compress) به عهده‌ی مدیر است

### ویژگی‌های تأخیری

- ویرایشگر ریچ‌تکست و سنیتایزر
- تاریخچه‌ی نسخه‌ها
- سیستم حسابرسی (Audit)
- مقصد product/brand در dashboard UI

---

## شبکه‌های اجتماعی (SocialLink — PR #9)

### بررسی کلی

لینک‌های شبکه‌های اجتماعی فروشگاه از طریق داشبورد اختصاصی مدیریت می‌شوند.
مدیر فروشگاه می‌تواند لینک‌ها را اضافه، ویرایش، حذف، فعال/غیرفعال کند و
محل نمایش (هدر، فوتر یا هر دو) را کنترل کند.

### پلتفرم‌های پشتیبانی‌شده

| پلتفرم | کد | آیکون |
|---------|-----|--------|
| اینستاگرام | `instagram` | instagram |
| تلگرام | `telegram` | telegram |
| واتساپ | `whatsapp` | whatsapp |
| لینکدین | `linkedin` | linkedin |
| ایکس / توییتر | `x` | x |
| یوتیوب | `youtube` | youtube |
| آپارات | `aparat` | aparat |
| فیسبوک | `facebook` | facebook |
| سفارشی | `custom` | link |

### مدیریت داشبورد

- مسیر: `/admin-panel/social-links/`
- سطح دسترسی: `@staff_required`
- ناوبری: سایدبار داشبورد → «شبکه‌های اجتماعی»

#### عملیات پشتیبانی‌شده

| عملیات | روش HTTP |
|--------|----------|
| فهرست | GET |
| ایجاد | GET (فرم) / POST (ذخیره) |
| ویرایش | GET (فرم) / POST (ذخیره) |
| حذف | POST فقط |
| فعال/غیرفعال | POST فقط |

#### فیلدهای فرم

- پلتفرم (platform) — انتخابی
- عنوان (title) — **الزامی** — برچسب دسترسی‌پذیری
- آدرس URL — **الزامی**
- ترتیب نمایش (display_order)
- فعال (is_active)
- نمایش در هدر (show_in_header)
- نمایش در فوتر (show_in_footer)

### نمایش هدر

لینک‌هایی که `is_active=True` و `show_in_header=True` باشند در هدر فروشگاه
قابل نمایش هستند. در حال حاضر هدر فروشگاه فضای اختصاصی برای شبکه‌های
اجتماعی ندارد — قابلیت ساختاری پشتیبانی می‌شود اما فقط فوتر بصری فعال است.

### نمایش فوتر

لینک‌هایی که `is_active=True` و `show_in_footer=True` باشند در فوتر فروشگاه
رندر می‌شوند. ترتیب: `display_order` صعودی، سپس `id` صعودی.

### ترتیب نمایش

- فیلد عددی `display_order` (PositiveIntegerField)
- Tiebreaker: `id` صعودی
- بدون drag-and-drop (عددی دستی)

### رفتار فعال/غیرفعال

- لینک‌های غیرفعال در هیچ‌جای فروشگاه رندر نمی‌شوند
- غیرفعال‌سازی از طریق POST به `/admin-panel/social-links/<id>/toggle/`

### امنیت URL

- فقط `https` و `http` مجاز
- `javascript:`, `data:`, `vbscript:` رد می‌شوند
- URL نسبی پروتکل (`//...`) رد می‌شود
- URL‌های ناقص/نامعتبر رد می‌شوند
- اعتبارسنجی سمت سرور با `validate_social_url()`
- خروجی‌ها توسط Django auto-escape محافظت می‌شوند
- هرگز `mark_safe()` روی محتوای کاربر استفاده نمی‌شود

### امنیت آیکون

- مدل هرگز HTML/SVG/CSS خام از دیتابیس بارگذاری نمی‌کند
- نگاشت `SOCIAL_ICON_MAP` فقط نام‌های مجاز را تعریف می‌کند
- فیلد `icon_name` فقط مقادیر از پیش تعریف‌شده را می‌پذیرد
- آیکون‌ها از طریق `partials/social_icon.html` با شرط‌بندی امن رندر می‌شوند
- پلتفرم‌های استاندارد آیکون خودکار دارند — `icon_name` دستی فقط برای override

### ویژگی‌های لینک خارجی

- `target="_blank"` — باز شدن در تب جدید
- `rel="noopener noreferrer"` — جلوگیری از دسترسی به `window.opener`
- `aria-label` — عنوان کاربر برای دسترسی‌پذیری

### وضعیت خالی (Empty State)

- بدون لینک فعال → بخش `.socials` در فوتر خالی رندر می‌شود (بدون `<a>`)
- هیچ لینک hardcoded با `href="#"` نمایش داده نمی‌شود
- سایر بخش‌های فوتر بدون تغییر باقی می‌مانند

### بهینه‌سازی Query

- یک query برای لینک‌های فوتر
- یک query برای لینک‌های هدر
- از context processor سراسری استفاده می‌شود (`apps.core.context_processors.shop_settings`)

### محدودیت‌های شناخته‌شده

- drag-and-drop ordering پیاده‌سازی نشده
- هدر فروشگاه فعلاً فضای بصری برای شبکه‌های اجتماعی ندارد (ساختار آماده)
- پیش‌نمایش آیکون در فرم داشبورد وجود ندارد
- تأیید حذف فقط JavaScript confirm()

### محدودیت‌های صریح (خارج از محدوده)

- Navigation Manager / Footer Builder
- Social login / OAuth
- Social sharing buttons
- Analytics tracking
- Multi-store support


---

## مدیریت منوهای ناوبری (Menu / MenuItem — PR #10)

### بررسی کلی

منوهای ناوبری فروشگاه از طریق داشبورد اختصاصی قابل مدیریت هستند. هر مکان
(هدر، فوتر، موبایل) حداکثر یک منوی فعال دارد. آیتم‌های منو از زیرساخت
DestinationMixin استفاده مجدد می‌کنند و حداکثر ۲ سطح سلسله‌مراتب پشتیبانی می‌شود.

### مکان‌های منو

| مکان | کد | توضیح |
|------|-----|--------|
| منوی اصلی | `header` | نوار ناوبری هدر فروشگاه |
| ستون اول فوتر | `footer_1` | ستون لینک‌های فوتر |
| ستون دوم فوتر | `footer_2` | ستون لینک‌های فوتر |
| ستون سوم فوتر | `footer_3` | ستون لینک‌های فوتر |
| منوی موبایل | `mobile` | ناوبری موبایل (ساختاری) |

- محدودیت یکتایی: هر مکان فقط یک منو دارد (unique constraint)
- مکان `mobile`: ساختاری پشتیبانی می‌شود — بصری فعال نیست (هیچ تغییری در layout موبایل)

### فیلدهای مدل Menu

| فیلد | نوع | توضیح |
|------|------|--------|
| `title` | CharField(150) | عنوان منو — الزامی |
| `location` | CharField(20) | مکان — unique, choices |
| `is_active` | BooleanField | فعال — default True |
| `created_at` | DateTimeField | auto_now_add |
| `updated_at` | DateTimeField | auto_now |

### فیلدهای مدل MenuItem

| فیلد | نوع | توضیح |
|------|------|--------|
| `menu` | ForeignKey(Menu) | منوی والد — PROTECT |
| `parent` | ForeignKey(self) | آیتم والد — PROTECT, nullable |
| `title` | CharField(200) | عنوان — الزامی |
| `display_order` | PositiveIntegerField | ترتیب — default 0 |
| `is_active` | BooleanField | فعال — default True |
| `open_in_new_tab` | BooleanField | تب جدید — default False |
| + فیلدهای DestinationMixin | | نوع مقصد، FK‌ها، URL خارجی |

### استفاده مجدد از DestinationMixin

آیتم‌های منو از همان زیرساخت مقصد امن PR #6 استفاده می‌کنند:
- نوع‌های مقصد: none, category, product, brand, external
- اعتبارسنجی انسجام مقصد
- حل URL با `resolve_destination_url()`
- امنیت URL خارجی (javascript/data/vbscript رد)
- حذف مقصد داخلی: SET_NULL → آیتم در رندر skip می‌شود

### محدودیت سلسله‌مراتب

- حداکثر **۲ سطح**: آیتم سطح اول + فرزند
- نوه (grandchild) مجاز **نیست**
- والد باید به **همان منو** تعلق داشته باشد
- آیتم نمی‌تواند والد **خودش** باشد
- آیتمی که فرزند دارد نمی‌تواند خودش فرزند شود
- روابط حلقوی رد می‌شوند

### ترتیب نمایش

- `display_order` صعودی
- Tiebreaker: `id` صعودی
- بدون drag-and-drop

### رفتار فعال/غیرفعال

- منوی غیرفعال: هیچ آیتمی رندر نمی‌شود
- آیتم غیرفعال: در رندر skip می‌شود
- والد غیرفعال: فرزندان هم رندر نمی‌شوند

### سیاست حذف

#### حذف منو
- منوی دارای آیتم **قابل حذف نیست** (PROTECT دستی در view)
- ابتدا باید آیتم‌ها حذف شوند
- پیام خطای فارسی به مدیر نمایش داده می‌شود

#### حذف آیتم والد
- آیتم والد با فرزند **قابل حذف نیست** (on_delete=PROTECT)
- ابتدا باید فرزندان حذف شوند
- پیام خطای فارسی

### امنیت لینک خارجی

- فقط طرح‌های مجاز (https, http, mailto, tel)
- `javascript:`, `data:`, `vbscript:` رد
- URL نسبی پروتکل رد
- خروجی‌ها Django auto-escape
- هرگز `mark_safe()` روی مقادیر دیتابیس
- `open_in_new_tab=True` → `target="_blank" rel="noopener noreferrer"`
- `open_in_new_tab=False` → بدون `target="_blank"`

### رندر هدر

- منوی فعال با `location=header` رندر می‌شود
- آیتم‌های سطح اول فعال و فرزندان فعال‌شان نمایش داده می‌شوند
- **زیرمنو**: والد با فرزندان فعال → dropdown قابل دسترس رندر می‌شود
  - والد با URL: لینک `<a>` + دکمه‌ی trigger جداگانه برای باز/بسته کردن زیرمنو
  - والد بدون URL: `<button>` به‌عنوان trigger (بدون `href="#"`)
  - فرزندان: `<ul class="nav-submenu">` با `<a>` برای هر فرزند
- **دسترسی‌پذیری**:
  - `aria-haspopup="true"` روی trigger
  - `:aria-expanded="open.toString()"` — وضعیت دینامیک
  - `aria-label` با نام منو برای trigger
  - `@keydown.escape` → بستن زیرمنو و بازگشت فوکوس به trigger
  - `@click.outside` → بستن زیرمنو
  - trigger عنصر `<button>` — keyboard-focusable
  - بدون trap فوکوس
- اگر منوی مدیریت‌شده وجود نداشته باشد → هیچ لینک ناوبری رندر نمی‌شود (بدون fallback)
- مقصد حل‌نشده → آیتم skip می‌شود
- والد موقت (بدون مقصد و بدون فرزند فعال) → رندر نمی‌شود

### رندر فوتر

- `footer_1`, `footer_2`, `footer_3` مستقل رندر می‌شوند
- عنوان منو به‌عنوان heading ستون فوتر استفاده می‌شود
- **سلسله‌مراتب در فوتر پشتیبانی می‌شود**: فرزندان به‌صورت `<ul>` تودرتو رندر می‌شوند
- والد بدون URL در فوتر: `<span>` (بدون `href="#"`)
- فرزندان غیرفعال یا unresolvable → حذف
- اگر منوی مدیریت‌شده وجود نداشته باشد → صفحات محتوایی (PR #7) به‌عنوان elif رندر می‌شوند
- ستون خالی (بدون آیتم رندرشدنی) → کل ستون حذف

### رندر موبایل

- ساختاری پشتیبانی می‌شود (`location=mobile`)
- بصری در این PR فعال **نیست** — منطقه‌ی بصری موبایل تغییر نکرده
- داده در context processor موجود است (`NAV_MOBILE`)

### گردش کار والد موقت (Provisional Parent)

- آیتم سطح اول با `destination_type=none` قابل ذخیره است (بدون نیاز به فرزند)
- در داشبورد نمایش داده می‌شود تا فرزند اضافه شود
- تا زمانی که فرزند فعال و معتبر ندارد → در فروشگاه رندر **نمی‌شود**
- پس از اضافه شدن فرزند معتبر → به‌عنوان heading زیرمنو رندر می‌شود
- نیازی به مقصد موقت/جعلی ندارد

### وضعیت خالی (Empty State)

- بدون منوی هدر فعال → هیچ لینک ناوبری هدر رندر نمی‌شود (بدون fallback)
- منوی فعال بدون آیتم رندرشدنی → هیچ لینکی تولید نمی‌شود
- فوتر بدون منوی مدیریت‌شده → صفحات محتوایی (اگر وجود داشته باشند) رندر
- هیچ لینک hardcoded جدیدی اضافه نشده
- هرگز `href="#"` تولید نمی‌شود

### بهینه‌سازی Query

- **۲ query** برای کل ناوبری:
  - ۱ query: منوهای فعال
  - ۱ query: آیتم‌های فعال با `select_related` (parent, destination_category, destination_product, destination_brand) — JOIN در یک query
- `Prefetch` با queryset سفارشی استفاده می‌شود
- بدون N+1 روی آیتم‌ها یا مقصدها
- تعداد query ثابت مستقل از تعداد منوها و آیتم‌ها
- Context processor: `apps.content.context_processors.navigation_menus`
- منوهای غیرفعال query نمی‌شوند (فقط `is_active=True`)

### مسیرهای داشبورد

| مسیر | عملیات |
|------|--------|
| `/admin-panel/menus/` | فهرست منوها |
| `/admin-panel/menus/add/` | افزودن منو |
| `/admin-panel/menus/<id>/edit/` | ویرایش منو |
| `/admin-panel/menus/<id>/delete/` | حذف منو (POST) |
| `/admin-panel/menus/<id>/toggle/` | فعال/غیرفعال (POST) |
| `/admin-panel/menus/<id>/items/` | فهرست آیتم‌ها |
| `/admin-panel/menus/<id>/items/add/` | افزودن آیتم |
| `/admin-panel/menu-items/<id>/edit/` | ویرایش آیتم |
| `/admin-panel/menu-items/<id>/delete/` | حذف آیتم (POST) |
| `/admin-panel/menu-items/<id>/toggle/` | فعال/غیرفعال (POST) |

- سطح دسترسی: `@staff_required`
- ناوبری: سایدبار → «مدیریت منوها»

### محدودیت‌های شناخته‌شده

- drag-and-drop ordering پیاده‌سازی نشده
- حداکثر ۲ سطح (بدون nesting عمیق)
- رندر موبایل بصری فعال نیست
- مقصد product/brand در فرم آیتم فعلاً hidden (مدل آماده)
- تأیید حذف فقط JavaScript confirm()
- Mega menu پشتیبانی نمی‌شود

### محدودیت‌های صریح (خارج از محدوده)

- Mega menus
- Unlimited-depth trees
- Footer Builder / Header Builder / Homepage Builder
- Product/Category redesign
- Multi-store support
- Navigation analytics
- Role-based menu visibility
- Scheduled publishing
- Wagtail / Generic page builder



---

## تنظیمات فوتر (FooterSettings — PR #11)

### تصمیم معماری

فوتر فروشگاه از طریق یک رکورد singleton (`FooterSettings`) با `pk=1` مدیریت می‌شود.
Django's `get_or_create` atomically handles concurrent first-load races — نیازی به
مدیریت دستی `IntegrityError` نیست.

### فیلدها

| فیلد | نوع | توضیح |
|------|------|--------|
| `is_enabled` | BooleanField | فعال/غیرفعال کل فوتر |
| `show_branding` | BooleanField | نمایش برندینگ |
| `show_logo` | BooleanField | نمایش لوگو |
| `description` | TextField(500) | توضیحات فوتر |
| `show_contact` | BooleanField | نمایش اطلاعات تماس |
| `address` | CharField(500) | آدرس |
| `phone` | CharField(50) | تلفن — validator: ارقام، فاصله، +، -، پرانتز |
| `secondary_phone` | CharField(50) | تلفن ثانویه — همان validator |
| `email` | EmailField | ایمیل |
| `working_hours` | CharField(250) | ساعات کاری |
| `show_navigation` | BooleanField | نمایش ناوبری |
| `show_social_links` | BooleanField | نمایش شبکه‌های اجتماعی |
| `show_newsletter` | BooleanField | نمایش خبرنامه |
| `newsletter_title` | CharField(150) | عنوان خبرنامه |
| `newsletter_description` | CharField(300) | توضیح خبرنامه |
| `show_trust_badges` | BooleanField | نمایش نمادهای اعتماد |
| `show_payment_logos` | BooleanField | نمایش لوگوهای پرداخت |
| `copyright_text` | CharField(300) | متن کپی‌رایت |

### رفتار singleton

- `load()` از `get_or_create(pk=1)` استفاده می‌کند
- `save()` همیشه `pk=1` را اجبار می‌کند
- حداکثر یک رکورد در دیتابیس وجود دارد
- ذخیره با pk متفاوت → نرمال‌سازی به pk=1

### نمادهای اعتماد (FooterTrustBadge)

- عنوان (الزامی)، تصویر (الزامی، حداکثر 5MB)، URL مقصد (اختیاری)
- ترتیب عددی (`display_order`)
- فعال/غیرفعال (`is_active`)
- URL خطرناک (`javascript:`, `data:`, `//`) رد می‌شود
- فقط وقتی `show_trust_badges=True` و حداقل یک badge فعال وجود دارد رندر می‌شود

### لوگوهای پرداخت (FooterPaymentLogo)

- عنوان (الزامی)، تصویر (الزامی، حداکثر 5MB)
- ترتیب عددی (`display_order`)
- فعال/غیرفعال (`is_active`)
- فقط وقتی `show_payment_logos=True` و حداقل یک logo فعال وجود دارد رندر می‌شود

### اعتبارسنجی تصویر

- حداکثر حجم: **5 مگابایت (5 MiB)** برای هر فایل
- validator: `validate_image_size()` روی فیلد `image`
- تصویر بزرگ‌تر → خطای اعتبارسنجی

### چرخه‌ی زندگی رسانه (Media Lifecycle)

- حذف badge/logo → فایل تصویر پس از commit حذف می‌شود
- جایگزینی تصویر → فایل قبلی پس از commit حذف
- شکست اعتبارسنجی → هیچ فایلی حذف نمی‌شود

### مسیرهای داشبورد

| مسیر | عملیات |
|------|--------|
| `/admin-panel/footer/settings/` | تنظیمات فوتر (GET/POST) |
| `/admin-panel/footer/trust-badges/add/` | افزودن نماد |
| `/admin-panel/footer/trust-badges/<id>/edit/` | ویرایش نماد |
| `/admin-panel/footer/trust-badges/<id>/delete/` | حذف نماد (POST) |
| `/admin-panel/footer/trust-badges/<id>/toggle/` | فعال/غیرفعال (POST) |
| `/admin-panel/footer/payment-logos/add/` | افزودن لوگو |
| `/admin-panel/footer/payment-logos/<id>/edit/` | ویرایش لوگو |
| `/admin-panel/footer/payment-logos/<id>/delete/` | حذف لوگو (POST) |
| `/admin-panel/footer/payment-logos/<id>/toggle/` | فعال/غیرفعال (POST) |

- سطح دسترسی: `@staff_required`

### کلیدهای قابل مشاهده (Visibility Toggles)

هر بخش فوتر قابل فعال/غیرفعال‌سازی مستقل است:
- `is_enabled`: کل فوتر
- `show_branding`: لوگو + توضیحات
- `show_contact`: اطلاعات تماس
- `show_navigation`: ستون‌های لینک (منوها)
- `show_social_links`: شبکه‌های اجتماعی
- `show_newsletter`: بخش خبرنامه (placeholder)
- `show_trust_badges`: نمادهای اعتماد
- `show_payment_logos`: لوگوهای پرداخت

### رندر تماس (Contact Rendering)

- تلفن: `<a href="tel:...">` — فقط وقتی مقدار غیرخالی
- ایمیل: `<a href="mailto:...">` — فقط وقتی مقدار غیرخالی
- آدرس: متن ساده
- ساعات کاری: متن ساده
- هرگز `href="#"` تولید نمی‌شود
- اعتبارسنجی تلفن: فقط ارقام، فاصله، +، -، پرانتز مجاز
- strip خودکار فاصله‌های ابتدا/انتها در `save()`

### یکپارچگی ناوبری / شبکه‌های اجتماعی / محتوا

- ناوبری فوتر: از منوهای مدیریت‌شده (PR #10) استفاده می‌کند
- شبکه‌های اجتماعی: از `SocialLink` (PR #9) با `show_in_footer=True`
- صفحات محتوایی: از `ContentPage` (PR #7) با `show_in_footer=True`

### خبرنامه (Newsletter Placeholder)

- `show_newsletter=True`: بخش خبرنامه با عنوان و برچسب «به‌زودی» رندر می‌شود
- پیاده‌سازی واقعی خبرنامه خارج از محدوده است

### وضعیت خالی (Empty State)

- فوتر غیرفعال → محتوای فوتر رندر نمی‌شود
- بخش badges بدون badge فعال → بخش حذف
- بخش logos بدون logo فعال → بخش حذف
- copyright خالی → بخش copyright حذف (بدون fallback hardcoded)
- هیچ مقدار hardcoded قدیمی بازنمی‌گردد

### کپی‌رایت (Copyright)

- اگر `copyright_text` دارای مقدار → رندر در `<span>` با auto-escape
- اگر `copyright_text` خالی → هیچ‌چیز رندر نمی‌شود (بدون fallback)
- هرگز `mark_safe()` استفاده نمی‌شود
- محتوای XSS توسط Django auto-escape خنثی می‌شود

### استراتژی Query (با شمارش دقیق)

| شرایط | تعداد Query |
|--------|-------------|
| هر دو media غیرفعال | 1 (فقط settings load) |
| badges فعال، logos غیرفعال | 2 |
| badges غیرفعال، logos فعال | 2 |
| هر دو media فعال | 3 |

- تعداد query مستقل از تعداد badge/logo (یک query برای هر نوع)
- `objects.none()` هیچ query اجرا نمی‌کند
- context processor: `apps.content.context_processors.footer_settings`

### محدودیت‌های شناخته‌شده

- drag-and-drop ordering پیاده‌سازی نشده
- پیش‌نمایش حجم فایل سمت کلاینت وجود ندارد
- خبرنامه placeholder (بدون پیاده‌سازی واقعی)
- بهینه‌سازی تصویر (resize/compress) به عهده‌ی مدیر

### محدودیت‌های صریح (خارج از محدوده)

- Footer Builder / Visual Editor
- Newsletter subscription backend
- Image CDN / optimization pipeline
- Multi-store footer
- A/B testing footer layouts
- Footer analytics
