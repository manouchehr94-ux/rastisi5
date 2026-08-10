"""StoryRailItem — آیتمِ ریلِ استوری. بخشِ مشترکِ اختیاریِ Builder
(هر خانواده‌ای می‌تواند اضافه‌اش کند). محتوایِ رسانه‌ای با مقصدِ امن."""

from django.db import migrations, models
import django.db.models.deletion
import apps.content.models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0017_scope_hero_slides_and_banners_to_section"),
        ("stores", "0001_initial"),
        ("storefront_builder", "0003_storefrontlayoutversion_appearance_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="StoryRailItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("destination_type", models.CharField(choices=[("none", "بدون لینک"), ("product", "صفحه\u200cی محصول"), ("category", "صفحه\u200cی دسته\u200cبندی"), ("brand", "صفحه\u200cی برند"), ("collection", "صفحه\u200cی کالکشن"), ("page", "صفحه\u200cی سفارشی"), ("external", "لینک خارجی")], default="none", max_length=20, verbose_name="نوع مقصد")),
                ("destination_product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="catalog.product", verbose_name="محصول مقصد")),
                ("destination_category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="catalog.category", verbose_name="دسته\u200cبندی مقصد")),
                ("destination_brand", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="catalog.brand", verbose_name="برند مقصد")),
                ("destination_collection", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="catalog.merchantcollection", verbose_name="کالکشن مقصد")),
                ("destination_external_url", models.URLField(blank=True, max_length=500, verbose_name="آدرس خارجی")),
                ("destination_open_new_tab", models.BooleanField(default=False, verbose_name="باز شدن در تب جدید")),
                ("title", models.CharField(blank=True, max_length=60, verbose_name="عنوان")),
                ("image", models.ImageField(upload_to="storyrail/", validators=[apps.content.models.validate_image_size, apps.content.models.validate_image_content], verbose_name="تصویر")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("display_order", models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="story_rail_items", to="stores.store", verbose_name="فروشگاه")),
                ("section", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="story_items", to="storefront_builder.storefrontsection", verbose_name="بخشِ سازنده بصری")),
            ],
            options={
                "verbose_name": "آیتم استوری",
                "verbose_name_plural": "آیتم\u200cهای استوری",
                "ordering": ["display_order", "id"],
            },
        ),
    ]
