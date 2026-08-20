"""Phase 2A — additive multi-block schema foundation.

این مهاجرت **هیچ رفتارِ اجرایی/رندریِ فعلی را تغییر نمی‌دهد** — فقط دو
ستونِ جدید، انتقالی و موازی به ``StorefrontSection`` اضافه می‌کند
(``cell``، ``cell_order``) و آن‌ها را از رویِ رابطه‌یِ قدیمیِ
``StorefrontCell.section`` (OneToOne، که بدونِ هیچ تغییری در همین
مهاجرت باقی می‌ماند) بک‌فیل می‌کند.

هدف: پایه‌گذاریِ schema برایِ Phase 2B آینده (چند section مرتب‌شده در
یک Cell) — بدونِ اینکه هیچ سرویس/ویو/تمپلیتِ رندریِ امروز از این
فیلدهایِ جدید بخواند یا بنویسد. مسیرِ اجراییِ تنها-معتبرِ امروز همچنان
``StorefrontCell.section`` است.

نگاه کنید به ``STOREFRONT_BUILDER_V3_AUDIT_REPORT.md`` (بخش‌های ۵ و ۹)
برایِ توضیحِ کاملِ چراییِ این استراتژیِ مرحله‌ایِ ۲A/۲B/۲C و چراییِ
افزودنِ یک فیلدِ **جدا** (``cell_order``) به‌جایِ استفاده‌یِ دوبارهِ
مبهم از ``StorefrontSection.order`` (که معنایِ سطحِ‌صفحه‌ایِ خودش را
بدونِ تغییر حفظ می‌کند).
"""

from django.db import migrations, models
import django.db.models.deletion


def backfill_section_cell(apps, schema_editor):
    """برایِ هر ``StorefrontCell`` که ``section_id`` دارد، Sectionِ مقابل
    را با ``cell_id = cell.id`` و ``cell_order = 0`` علامت‌گذاریِ *موازی*
    می‌کند — رابطه‌یِ قدیمیِ ``cell.section`` دست‌نخورده باقی می‌ماند.

    این تابع عمداً به‌جایِ کوئریِ رویِ ``StorefrontSection`` از رویِ
    ``StorefrontCell`` پیمایش می‌کند: تنها منبعِ حقیقتِ *امروز* برایِ
    «کدام section در کدام cell است؟» همان OneToOne قدیمی است — بک‌فیل
    باید همیشه از رویِ همان منبع خوانده شود، نه از رویِ فیلدِ تازه‌ای که
    خودش قرار است نتیجه‌یِ همین بک‌فیل باشد.

    Idempotent: اجرایِ دوباره‌یِ همین تابع (مثلاً در یک محیطِ تستِ که
    مهاجرت‌ها دوبار اجرا می‌شوند) نتیجه‌یِ یکسانی تولید می‌کند، چون همیشه
    از رویِ OneToOneِ فعلی (نه از رویِ حالتِ قبلیِ خودِ فیلدِ جدید) دوباره
    محاسبه می‌شود.
    """
    StorefrontCell = apps.get_model("storefront_builder", "StorefrontCell")
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")

    populated_cells = StorefrontCell.objects.filter(section_id__isnull=False).only(
        "id", "section_id"
    )
    for cell in populated_cells.iterator():
        StorefrontSection.objects.filter(pk=cell.section_id).update(
            cell_id=cell.pk, cell_order=0
        )


def reverse_backfill_section_cell(apps, schema_editor):
    """بازگشتِ داده‌ایِ ایمن: تمامِ مقادیرِ ``cell``/``cell_order`` را به
    حالتِ خالی/پیش‌فرض برمی‌گرداند. رابطه‌یِ قدیمیِ ``cell.section``
    هرگز توسطِ این مهاجرت (در هیچ جهتی) تغییر نکرده، پس این بازگشت
    هیچ داده‌یِ واقعی/اجرایی‌ای را از دست نمی‌دهد."""
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")
    StorefrontSection.objects.filter(cell_id__isnull=False).update(cell_id=None, cell_order=0)


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0014_storefront_container_cell_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="storefrontsection",
            name="cell",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="blocks",
                to="storefront_builder.storefrontcell",
                verbose_name="خانه (Cell)",
                # این متن باید دقیقاً (بایت‌به‌بایت) با help_text فیلدِ
                # StorefrontSection.cell در models.py یکسان باشد — در غیرِ
                # این صورت `makemigrations --check --dry-run` یک AlterField
                # اضافیِ ۰۰۱۶ پیشنهاد می‌دهد (دقیقاً همان دریفتی که این
                # مهاجرت پیش از این اصلاح داشت).
                help_text=(
                    "Phase 2A (پایه‌یِ چندبلاکیِ Cell — نگاه کنید به گزارشِ ممیزیِ "
                    "V3، بخشِ ۵/۹): ارجاعِ **موازی و انتقالی** به Cellی که این section "
                    "در آن قرار گرفته — مکملِ (نه جایگزینِ) رابطه‌یِ قدیمیِ "
                    "``StorefrontCell.section`` (OneToOne) که همچنان تنها منبعِ "
                    "حقیقتِ *اجراییِ* امروز است. در Phase 2A این فیلد فقط با "
                    "بک‌فیلِ مهاجرت پر می‌شود و هیچ سرویس/ویو/تمپلیتِ رندر از آن "
                    "نمی‌خوانَد — معماریِ آماده‌برایِ‌آینده برایِ Phase 2B (چند بلاکِ "
                    "مرتب‌شده در یک Cell)، نه یک مسیرِ رندرِ فعال. NULL یعنی این "
                    "section هرگز داخلِ هیچ Cellی قرار نگرفته (اکثریتِ قریب‌به‌اتفاقِ "
                    "sectionهایِ امروز)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="storefrontsection",
            name="cell_order",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="ترتیب داخلِ Cell",
                # همان الزامِ تطبیقِ بایت‌به‌بایت بالا — نگاه کنید به
                # StorefrontSection.cell_order در models.py.
                help_text=(
                    "فقط وقتی cell خالی (NULL) نباشد معنا دارد — ترتیبِ این section "
                    "در میانِ بلاک‌هایِ همان Cell (Phase 2B: چند section در یک Cell). "
                    "**عمداً جدا از فیلدِ ``order`` بالاست** — ``order`` معنایِ "
                    "قدیمیِ/سطحِ‌صفحه‌ایِ خودش را (ترتیبِ این section در میانِ همه‌یِ "
                    "sectionهایِ همان Page) کاملاً بدونِ تغییر حفظ می‌کند؛ استفاده‌یِ "
                    "دوباره از ``order`` برایِ این معنایِ دوم (به‌شرطِ NULL/غیر-NULL "
                    "بودنِ cell) دقیقاً همان الگویِ «فیلدِ دوپهلو/دو-معنایی» است که "
                    "گزارشِ ممیزی (بخشِ ۵) صریحاً رد کرده — از جمله چون "
                    "``Meta.ordering = ['order', 'id']`` رویِ کوئری‌هایِ ترکیبی "
                    "(section هایِ داخلِ Cell و بیرونِ Cell در یک صفحه) نتیجه‌یِ "
                    "نادرست می‌داد. پیش‌فرضِ ۰ برایِ همه‌یِ sectionهایِ بدونِ cell "
                    "(اکثریتِ قریب‌به‌اتفاق) بی‌اثر است."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="storefrontsection",
            constraint=models.UniqueConstraint(
                fields=("cell", "cell_order"),
                condition=models.Q(cell__isnull=False),
                name="storefront_section_unique_cell_order_per_cell",
            ),
        ),
        migrations.RunPython(backfill_section_cell, reverse_backfill_section_cell),
    ]
