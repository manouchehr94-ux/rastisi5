from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_shipping_free_over_optional_and_cost_check"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="gift_wrap_selected",
            field=models.BooleanField(default=False, verbose_name="کادوپیچی انتخاب شده"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="gift_wrap_unit_price",
            field=models.DecimalField(
                decimal_places=0, default=0, max_digits=12,
                verbose_name="هزینه\u200cی کادوپیچی (اسنپ\u200cشات)",
            ),
        ),
    ]
