import re

from django.db import migrations, models

_FA_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_AR_TO_FA_LETTERS = str.maketrans({"ي": "ی", "ك": "ک"})
_WHITESPACE_RE = re.compile(r"\s+")


def _normalization_key(value):
    text = (value or "").translate(_FA_TO_EN).translate(_AR_TO_FA_LETTERS)
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def backfill_variants_and_product_type(apps, schema_editor):
    """مقادیر normalized_attribute/normalized_value رکوردهای موجود را پر می‌کند، و کالاهایی
    که از قبل تنوع فعال دارند را «دارای تنوع» علامت می‌زند (تا رفتار فروشگاهی فعلی حفظ شود)."""
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    Product = apps.get_model("catalog", "Product")

    for variant in ProductVariant.objects.all():
        variant.normalized_attribute = _normalization_key(variant.attribute)
        variant.normalized_value = _normalization_key(variant.value)
        variant.save(update_fields=["normalized_attribute", "normalized_value"])

    # اگر بیش از یک تنوع فعال با کلید نرمال‌شده‌ی یکسان روی یک کالا موجود بود (داده‌ی قدیمی‌تر
    # از این قید)، فقط قدیمی‌ترین را فعال نگه می‌دار تا Constraint بعدی این migration شکست نخورد.
    seen = {}
    for variant in ProductVariant.objects.filter(is_active=True).order_by("product_id", "id"):
        key = (variant.product_id, variant.normalized_attribute, variant.normalized_value)
        if key in seen:
            variant.is_active = False
            variant.save(update_fields=["is_active"])
        else:
            seen[key] = variant.id

    variable_product_ids = ProductVariant.objects.values_list("product_id", flat=True).distinct()
    Product.objects.filter(id__in=list(variable_product_ids)).update(product_type="variable")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_specification_specificationtemplate_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_variants_and_product_type, noop_reverse),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("product", "normalized_attribute", "normalized_value"),
                name="uniq_active_variant_value_per_product",
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(
                condition=models.Q(("sku", ""), _negated=True),
                fields=("sku",),
                name="uniq_variant_sku_when_set",
            ),
        ),
    ]
