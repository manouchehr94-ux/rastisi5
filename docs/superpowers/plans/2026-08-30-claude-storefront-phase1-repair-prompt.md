# پرامپت جامع Claude Code — RastiSi Storefront Builder Phase 1 Repair

تو روی پروژه RastiSi کار می‌کنی. این یک **فاز تشخیص و اصلاح دقیق** است، نه redesign و نه بازنویسی.

## محیط و branch

Repository: `manouchehr94-ux/rastisi5`
Worktree پیشنهادی: `D:\Projects\RastiSi4_Claude_Storefront_Phase1`
Branch الزامی: `claude/storefront-builder-phase1-repair`
Trusted remote: `rastisi5`

ابتدا این‌ها را اجرا و گزارش کن:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git remote -v
```

اگر branch درست نیست، STOP کن. به branch دیگری switch/merge/rebase نکن.

**ممنوع:** force push، merge، rebase، pull، reset --hard، clean، دست‌زدن به branch احراز هویت/onboarding یا branch رسمی storefront.

## اسناد اجباری قبل از تغییر کد

کامل بخوان:

- `docs/superpowers/specs/2026-08-30-claude-storefront-phase1-repair-design.md`
- `docs/superpowers/plans/2026-08-30-claude-storefront-phase1-repair.md`
- تست‌های R2/R3/R3.2/Universal Selection فعلی

Phase 2 را فعلاً اجرا نکن. فقط فایل deferred plan آن را برای context ببین.

## وضعیت فعلی که باید واقعاً بررسی کنی

R3 full-screen live Builder باز می‌شود و modal ویرایش تقریباً 70% صفحه است. مشکل فعلی داخل modal است:

1. در بخش‌هایی مثل دسته‌بندی/برند/کالکشن، `انتخاب خودکار` و `انتخاب دستی` دیده می‌شوند ولی کلیک روی آن‌ها هیچ UI مرتبطی را باز/فعال نمی‌کند.
2. تنظیمات پس‌زمینه و احتمالاً چند تنظیم تعاملی دیگر هم کار نمی‌کنند یا persist نمی‌شوند.
3. داخل فرم یک دکمه `ذخیره تنظیمات` داریم و پایین modal یک دکمه `انجام شد`.
4. قرارداد مطلوب:
   - `ذخیره تنظیمات`: **همان فرم فعال را save کند و modal باز بماند**.
   - `انجام شد`: **همان save را انجام دهد؛ فقط بعد از موفقیت modal را ببندد و preview را refresh کند**.
   - روی validation/server error modal بسته نشود و خطا دیده شود.
   - double-submit نداشته باشیم.
   - دو persistence implementation مستقل نساز.
5. احتمال دارد مشکل shared lifecycle باشد چون چند کنترل هم‌زمان از کار افتاده‌اند. فرض نکن؛ prove کن.

## روش کار الزامی

### 1) اول تشخیص، بعد اصلاح

مسیر زیر را end-to-end trace کن:

`Preview click -> R3 parent modal -> HTMX GET/swap -> Alpine/component init -> interaction -> form submission/autosave -> Django save -> preview refresh -> modal close/keep-open`

به‌خصوص این فایل‌ها را بررسی کن:

- `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html`
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/r3_edit_modal.html`
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_settings_form.html`
- `apps/storefront_builder/templates/dashboard/storefront_builder/partials/universal_selection_picker.html`
- partialهای background/responsive/motion/destination
- `apps/storefront_builder/views.py`

HTMX events و Alpine initialization پس از swap را بررسی کن. اگر مشکل hydration/init است با evidence نشان بده. اگر نیست، root cause واقعی را trace کن.

قبل از production change یک یادداشت کوتاه با این قالب بده:

```text
ROOT CAUSE:
EVIDENCE:
WORKING PATH COMPARISON:
MINIMAL FIX BOUNDARY:
```

### 2) TDD واقعی

برای root cause یک regression بنویس و اول RED را نشان بده. سپس minimal fix و GREEN.

برای save contract هم حداقل سه regression لازم است:

- Save داخلی: persist + modal stays open.
- Done: persist + wait success + close + preview refresh.
- Error: no close + visible error.

تست را بعد از کد ننویس.

### 3) Backend را بی‌دلیل بازطراحی نکن

این زیرساخت‌ها باید حفظ شوند:

- StorefrontSection / StorefrontContainer / StorefrontCell
- Draft / Preview / Publish / History
- Palette64
- template/palette/appearance persistence فعلی
- section registry / renderer / endpoints فعلی تا جایی که root cause نیاز به تغییر مشخص نداشته باشد
- dark_digital و templateهای موجود

Model/migration جدید فقط اگر evidence واضح نشان دهد ضروری است؛ انتظار فعلی این است که لازم نباشد.

## Browser QA اجباری بعد از fix

با data واقعی QA تست کن. اگر `db.sqlite3` در worktree هست از آن استفاده کن؛ media را در صورت نیاز از QA media path موجود پروژه تنظیم کن.

حداقل:

1. Category section:
   - automatic/manual switch
   - manual selection/reorder/remove
   - save
   - preview reflects result
2. Brand section:
   - از تعداد زیاد برند فقط 5 برند انتخاب کن
   - ترتیب را تغییر بده
   - save
   - فقط همان‌ها در preview دیده شوند
3. Collection section: automatic/manual + reorder + save.
4. Product section: automatic sources + manual product selection/search.
5. Background: mode/color/palette related controls interact and persist.
6. Display mode/item count.
7. Responsive/motion/destination و سایر settings موجود همان section.
8. Header/Footer editor modal و Back.
9. Edit mode نباید customer login را باز کند.
10. `ذخیره تنظیمات` modal را نبندد.
11. `انجام شد` بعد از save موفق modal را ببندد.

اگر defect جدید مستقل پیدا شد، برای همان defect دوباره RED -> root cause -> minimal fix -> GREEN؛ patch تصادفی روی symptom نزن.

## Verification نهایی

حداقل اجرا و گزارش کن:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.storefront_builder.tests --keepdb
git diff --check
```

اگر full suite پروژه command دیگری در repo دارد، همان baseline رسمی را هم اجرا کن.

## Git پایان Phase 1

فقط وقتی automated + browser QA قابل قبول است:

- intended files را review کن.
- commit focused بساز.
- normal push به `rastisi5 claude/storefront-builder-phase1-repair`.
- force push ممنوع.

گزارش نهایی باید شامل این‌ها باشد:

```text
BASELINE SHA:
FINAL SHA:
ROOT CAUSE:
FILES CHANGED:
TESTS + COUNTS:
BROWSER QA:
MIGRATION DRIFT:
GIT DIFF CHECK:
KNOWN GAPS:
```

**بعد STOP کن. Phase 2 را شروع نکن تا من صریحاً بگویم Phase 1 تأیید شد.**
