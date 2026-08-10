from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0006_coupon_store_enforce_not_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="gift_wrap_selected",
            field=models.BooleanField(default=False, verbose_name="کادوپیچی انتخاب شده"),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="gift_wrap_unit_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=12,
                verbose_name="هزینه\u200cی کادوپیچی (اسنپ\u200cشات)",
            ),
        ),
    ]
