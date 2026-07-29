import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0005_backfill_coupon_store"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coupon",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="coupons",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AddConstraint(
            model_name="coupon",
            constraint=models.UniqueConstraint(
                fields=("store", "code"), name="uniq_coupon_code_per_store"
            ),
        ),
    ]
