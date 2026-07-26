import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_backfill_orders_store"),
        ("stores", "0002_create_akhlaghi_store"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AlterField(
            model_name="paymentgateway",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payment_gateways",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AlterField(
            model_name="shippingmethod",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shipping_methods",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
    ]
