"""ProductMetafield — متادیتایِ توسعه‌پذیرِ محصول. مکانیزمِ مشترک برایِ
سایزگاید، سازنده/منطقه (artisan)، و هر نوع متادیتایِ ساختاریِ آینده.
جایگزینِ فیلدهایِ تک‌منظوره‌ی خانواده‌محور."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0037_category_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductMetafield",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("namespace", models.CharField(db_index=True, help_text="دسته\u200cبندیِ منطقی: size_guide, artisan, specs, custom", max_length=40, verbose_name="فضای نام")),
                ("key", models.CharField(help_text="کلیدِ مشخص: chart_html, maker, region, material, dimensions", max_length=60, verbose_name="کلید")),
                ("value_text", models.TextField(blank=True, default="", help_text="برای متن ساده، HTML امن (سایزگاید)، یا مقادیرِ کوتاه.", verbose_name="مقدارِ متنی")),
                ("value_json", models.JSONField(blank=True, default=None, help_text="برای داده\u200cی ساختاری: جدول سایز، لیست ویژگی\u200cها و...", null=True, verbose_name="مقدارِ ساختاری")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metafields", to="catalog.product", verbose_name="کالا")),
            ],
            options={
                "verbose_name": "متادیتای کالا",
                "verbose_name_plural": "متادیتاهای کالا",
                "ordering": ["namespace", "key"],
            },
        ),
        migrations.AddConstraint(
            model_name="productmetafield",
            constraint=models.UniqueConstraint(fields=("product", "namespace", "key"), name="uniq_product_metafield"),
        ),
    ]
