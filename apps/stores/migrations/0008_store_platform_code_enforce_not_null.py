from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0007_backfill_store_platform_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="store",
            name="platform_code",
            field=models.CharField(
                max_length=9,
                unique=True,
                editable=False,
                verbose_name="کد پایدار پلتفرم",
                help_text=(
                    "شناسه‌ی ۹ نویسه‌ای پایدار و قابل‌تایپ (ADR-94) — پایه‌ی "
                    "نام میزبان آزمایشی «{code}.rastisi.ir». برخلاف public_id "
                    "(UUID، برای ارجاع فنی) یا admin_subdomain (میزبان پنل "
                    "مدیریت)، هرگز تغییر نمی‌کند و هرگز به فروشگاه دیگری "
                    "واگذار نمی‌شود، حتی پس از تغییر زیردامنه‌ی عمومی."
                ),
            ),
        ),
    ]
