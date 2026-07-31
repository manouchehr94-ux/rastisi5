from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stores", "0008_store_platform_code_enforce_not_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="storedomain",
            name="domain_type",
            field=models.CharField(
                choices=[
                    ("generated_trial", "زیردامنه‌ی آزمایشی خودکار"),
                    ("platform_subdomain", "زیردامنه‌ی انتخابی روی rastisi.ir"),
                    ("custom_domain", "دامنه‌ی اختصاصی"),
                ],
                db_index=True,
                default="custom_domain",
                max_length=20,
                verbose_name="نوع دامنه",
                help_text=(
                    "توصیفی است، نه تعیین‌کننده‌ی مسیریابی (ADR-95) — واجد "
                    "شرایط بودن برای مسیریابی همچنان فقط از verification_"
                    "status/Store.status می‌آید. زیردامنه‌های آزمایشی/انتخابی "
                    "روی rastisi.ir از ابتدا verified ساخته می‌شوند چون "
                    "Rastisi خودش مالک DNS آن زیردامنه‌هاست؛ فقط custom_"
                    "domain مسیر تأیید واقعی را طی می‌کند."
                ),
            ),
        ),
        migrations.AddField(
            model_name="storedomain",
            name="is_redirect",
            field=models.BooleanField(
                default=False,
                verbose_name="فقط تغییرمسیر (نام میزبان بازنشسته)",
                help_text=(
                    "وقتی True، این نام میزبان دیگر محتوای فروشگاه را "
                    "مستقیماً نمایش نمی‌دهد — فقط برای همیشه به دامنه‌ی "
                    "اصلی فعلی فروشگاه تغییرمسیر می‌دهد (ADR-96)، پس از "
                    "این‌که مالک زیردامنه‌ی خواناتری خریداری/انتخاب کرده "
                    "باشد. توسط HostnameRedirectMiddleware اعمال می‌شود، "
                    "نه توسط resolution.py."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="storedomain",
            constraint=models.CheckConstraint(
                check=~models.Q(is_redirect=True) | models.Q(is_primary=False),
                name="redirect_alias_domain_is_never_primary",
            ),
        ),
    ]
