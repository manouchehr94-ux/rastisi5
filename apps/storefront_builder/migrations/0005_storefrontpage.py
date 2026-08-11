# Phase 1A — Universal Page Architecture (owner decisions 2/3): introduce
# StorefrontPage beneath StorefrontLayoutVersion. Purely additive — new,
# empty table, zero impact on existing StorefrontSection rows (which still
# FK directly to StorefrontLayoutVersion at this point in the migration
# sequence; that FK is only removed in migration 0010, after every
# existing section has been safely backfilled onto a page in 0008).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0004_storefrontsection_stable_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorefrontPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("page_type", models.CharField(
                    choices=[
                        ("home", "صفحه اصلی"),
                        ("product_detail", "جزئیات محصول"),
                        ("listing", "لیست محصولات"),
                        ("collection", "کالکشن"),
                        ("search", "نتایج جستجو"),
                        ("cart", "سبد خرید"),
                    ],
                    max_length=20, verbose_name="نوع صفحه",
                )),
                ("version", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="pages", to="storefront_builder.storefrontlayoutversion",
                    verbose_name="نسخه چیدمان",
                )),
            ],
            options={
                "verbose_name": "صفحه چیدمان فروشگاه",
                "verbose_name_plural": "صفحات چیدمان فروشگاه",
            },
        ),
        migrations.AddConstraint(
            model_name="storefrontpage",
            constraint=models.UniqueConstraint(
                fields=("version", "page_type"),
                name="storefront_page_unique_type_per_version",
            ),
        ),
    ]
