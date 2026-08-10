from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_shopsettings_tax_setup_confirmed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopsettings",
            name="gift_wrap_available",
            field=models.BooleanField(default=False, verbose_name="کادوپیچی در دسترس است"),
        ),
        migrations.AddField(
            model_name="shopsettings",
            name="gift_wrap_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=12,
                verbose_name="هزینه\u200cی کادوپیچی (تومان، هر قلم)",
            ),
        ),
    ]
