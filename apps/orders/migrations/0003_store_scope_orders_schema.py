# Hand-written (not machine-generated) — staged Store-ownership migration,
# stage 1 of 3 (schema, nullable). Mirrors
# apps/catalog/migrations/0006_store_scope_catalog_schema.py's structure:
# nullable schema now -> backfill in 0004 -> enforce NOT NULL in 0005.
#
# `Order.store`/`PaymentGateway.store`/`ShippingMethod.store` are added
# nullable here specifically so existing rows can be backfilled in a
# separate, auditable data migration before the NOT NULL constraint is
# enforced — the standard safe pattern for adding a required FK to a table
# that may already contain data.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_order_tracking_code"),
        ("stores", "0002_create_akhlaghi_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="idempotency_key",
            field=models.CharField(
                blank=True, default="", max_length=64, verbose_name="کلید یکتای درخواست تسویه‌حساب"
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="store",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="sku",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="کد کالا (SKU) (اسنپ‌شات)"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="variant_label",
            field=models.CharField(blank=True, default="", max_length=150, verbose_name="تنوع انتخاب‌شده (اسنپ‌شات)"),
        ),
        migrations.AddField(
            model_name="paymentgateway",
            name="store",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payment_gateways",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AddField(
            model_name="shippingmethod",
            name="store",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shipping_methods",
                to="stores.store",
                verbose_name="فروشگاه",
            ),
        ),
        migrations.AlterField(
            model_name="paymentgateway",
            name="slug",
            field=models.SlugField(allow_unicode=True, max_length=120, verbose_name="اسلاگ"),
        ),
        migrations.AlterField(
            model_name="shippingmethod",
            name="slug",
            field=models.SlugField(allow_unicode=True, max_length=120, verbose_name="اسلاگ"),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key", ""), _negated=True),
                fields=("idempotency_key",),
                name="uniq_order_idempotency_key_when_set",
            ),
        ),
        migrations.AddConstraint(
            model_name="paymentgateway",
            constraint=models.UniqueConstraint(
                fields=("store", "slug"), name="uniq_paymentgateway_slug_per_store"
            ),
        ),
        migrations.AddConstraint(
            model_name="shippingmethod",
            constraint=models.UniqueConstraint(
                fields=("store", "slug"), name="uniq_shippingmethod_slug_per_store"
            ),
        ),
    ]
