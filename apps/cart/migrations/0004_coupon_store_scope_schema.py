import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0003_cart_checkout_token"),
        ("stores", "0002_create_akhlaghi_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="coupon",
            name="store",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="coupons",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AlterField(
            model_name="coupon",
            name="code",
            field=models.CharField(max_length=30, verbose_name="کد تخفیف"),
        ),
    ]
