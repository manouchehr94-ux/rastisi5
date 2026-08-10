"""اضافه‌کردنِ فیلد تصویر به مدل Category — تصویر واقعی برای نمایش در
Family templateها (تایل/بنر/پرتره) با جایگزینِ emoji fallback."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0036_merchantcollection_source_legacy_product_tag"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="image",
            field=models.ImageField(
                blank=True,
                help_text="تصویر واقعی برای نمایش در کارت/تایلِ دسته\u200cبندی. اگر خالی باشد، آیکون (ایموجی) به\u200cعنوان جایگزین نمایش داده می\u200cشود.",
                null=True,
                upload_to="categories/images/",
                verbose_name="تصویر دسته\u200cبندی",
            ),
        ),
    ]
