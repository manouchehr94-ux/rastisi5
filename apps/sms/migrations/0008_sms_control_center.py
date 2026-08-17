# Generated for RastiSi SMS Control Center
from django.db import migrations, models


def seed_policy_and_templates(apps, schema_editor):
    Policy = apps.get_model("sms", "SmsBillingPolicy")
    Policy.objects.get_or_create(pk=1, defaults={
        "chars_per_credit": 70, "price_per_credit_toman": 205, "otp_overdraft_limit": 10,
    })
    Template = apps.get_model("sms", "SmsTemplate")
    Template.objects.get_or_create(
        event_key="platform_owner_otp",
        defaults={
            "title": "OTP ثبت‌نام / ورود مالک فروشگاه",
            "body": "کد تأیید راستیسی: {otp_code}\nاین کد تا {expire_minutes} دقیقه معتبر است.",
            "is_active": True,
        },
    )
    Template.objects.get_or_create(
        event_key="platform_test",
        defaults={"title": "تست زیرساخت پیامک", "body": "پیامک آزمایشی راستیسی", "is_active": True},
    )
    Template.objects.get_or_create(
        event_key="notification",
        defaults={"title": "اعلان عمومی / امنیتی", "body": "{message}", "is_active": True},
    )

    Log = apps.get_model("sms", "SmsLog")
    for log in Log.objects.all().iterator():
        original = log.message or ""
        chars = len(original)
        units = (chars + 69) // 70 if chars else 0
        log.character_count = chars
        log.billable_units = units
        # این پیام‌ها پیش از فعال‌شدن سیاست جدید ارسال شده‌اند؛ قیمت تاریخی
        # قابل اثبات نیست، پس هزینه جعلی 205 تومان برای گذشته ثبت نمی‌کنیم.
        log.unit_price_toman = 0
        log.cost_toman = 0
        if log.event_key in {"otp", "platform_owner_otp"}:
            log.message = ""
        log.save(update_fields=[
            "message", "character_count", "billable_units", "unit_price_toman", "cost_toman",
        ])


class Migration(migrations.Migration):
    dependencies = [("sms", "0007_platform_owner_admin_gap_fill")]
    operations = [
        migrations.AddField(model_name="smstemplate", name="melipayamak_body_id", field=models.CharField(blank=True, default="", help_text="شناسه الگوی تاییدشده در وب‌سرویس خدماتی ملی‌پیامک.", max_length=30, verbose_name="BodyId ملی‌پیامک")),
        migrations.AddField(model_name="smstemplate", name="melipayamak_variables_order", field=models.CharField(blank=True, default="otp_code", help_text="نام متغیرها به ترتیب Pattern؛ مثال: otp_code,expire_minutes", max_length=255, verbose_name="ترتیب متغیرهای ملی‌پیامک")),
        migrations.AddField(model_name="smstemplate", name="kavenegar_template", field=models.CharField(blank=True, default="", help_text="نام قالب VerifyLookup برای پیام‌های OTP.", max_length=100, verbose_name="Template کاوه‌نگار")),
        migrations.CreateModel(name="SmsBillingPolicy", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
            ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
            ("chars_per_credit", models.PositiveIntegerField(default=70, verbose_name="کاراکتر در هر اعتبار")),
            ("price_per_credit_toman", models.PositiveIntegerField(default=205, verbose_name="قیمت هر اعتبار (تومان)")),
            ("otp_overdraft_limit", models.PositiveIntegerField(default=10, verbose_name="سقف بدهی OTP")),
        ], options={"verbose_name": "سیاست هزینه پیامک", "verbose_name_plural": "سیاست هزینه پیامک"}),
        migrations.AddField(model_name="smslog", name="provider", field=models.CharField(blank=True, default="", max_length=20, verbose_name="شرکت پیامکی")),
        migrations.AddField(model_name="smslog", name="character_count", field=models.PositiveIntegerField(default=0, verbose_name="تعداد کاراکتر")),
        migrations.AddField(model_name="smslog", name="billable_units", field=models.PositiveIntegerField(default=0, verbose_name="تعداد اعتبار مصرفی")),
        migrations.AddField(model_name="smslog", name="unit_price_toman", field=models.PositiveIntegerField(default=0, verbose_name="قیمت هر اعتبار (تومان)")),
        migrations.AddField(model_name="smslog", name="cost_toman", field=models.PositiveBigIntegerField(default=0, verbose_name="هزینه نهایی (تومان)")),
        migrations.AddField(model_name="smslog", name="balance_before", field=models.IntegerField(blank=True, null=True, verbose_name="اعتبار قبل")),
        migrations.AddField(model_name="smslog", name="balance_after", field=models.IntegerField(blank=True, null=True, verbose_name="اعتبار بعد")),
        migrations.AlterField(model_name="smslog", name="event_key", field=models.CharField(choices=[("platform_owner_otp", "OTP ثبت‌نام / ورود مالک فروشگاه"), ("platform_test", "تست زیرساخت پیامک"), ("notification", "اعلان عمومی / امنیتی"), ("welcome", "ثبت‌نام / خوش‌آمدگویی"), ("otp", "کد ورود یکبار مصرف"), ("order_placed", "ثبت سفارش"), ("payment_success", "پرداخت موفق"), ("payment_failed", "پرداخت ناموفق"), ("order_processing", "سفارش در حال پردازش"), ("order_shipped", "ارسال سفارش"), ("order_delivered", "تحویل سفارش"), ("order_canceled", "لغو سفارش")], max_length=30, verbose_name="رویداد")),
        migrations.AlterField(model_name="smstemplate", name="event_key", field=models.CharField(choices=[("platform_owner_otp", "OTP ثبت‌نام / ورود مالک فروشگاه"), ("platform_test", "تست زیرساخت پیامک"), ("notification", "اعلان عمومی / امنیتی"), ("welcome", "ثبت‌نام / خوش‌آمدگویی"), ("otp", "کد ورود یکبار مصرف"), ("order_placed", "ثبت سفارش"), ("payment_success", "پرداخت موفق"), ("payment_failed", "پرداخت ناموفق"), ("order_processing", "سفارش در حال پردازش"), ("order_shipped", "ارسال سفارش"), ("order_delivered", "تحویل سفارش"), ("order_canceled", "لغو سفارش")], max_length=30, unique=True, verbose_name="رویداد")),
        migrations.RunPython(seed_policy_and_templates, migrations.RunPython.noop),
    ]
