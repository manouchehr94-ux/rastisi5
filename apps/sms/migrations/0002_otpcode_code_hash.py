from django.db import migrations, models


class Migration(migrations.Migration):
    """OtpCode.code (plaintext) becomes code_hash (hashed) - see
    apps.sms.services.otp_service (auth-unification pass). OTP codes are
    2-minute-lived and never meant to be read back once issued, so no data
    migration is needed: any row that survives this migration (already
    expired in practice) simply becomes permanently unverifiable, which is
    the same outcome as it expiring normally.
    """

    dependencies = [
        ("sms", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="otpcode",
            name="code",
        ),
        migrations.AddField(
            model_name="otpcode",
            name="code_hash",
            field=models.CharField(default="", max_length=200, verbose_name="هَشِ کد"),
            preserve_default=False,
        ),
    ]
