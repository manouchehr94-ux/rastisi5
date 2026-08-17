import uuid

from django.db import migrations, models
import django.db.models.deletion


PRESET_BY_SPANS = {
    (12,): "single",
    (6, 6): "half",
    (3, 9): "quarter_left",
    (9, 3): "quarter_right",
    (4, 8): "third_left",
    (8, 4): "third_right",
    (4, 4, 4): "thirds",
    (3, 3, 3, 3): "quarters",
}

DEFAULT_SETTINGS = {
    "gap": 14,
    "mobile_mode": "stack",
    "content_width": "standard",
    "vertical_align": "stretch",
}


def _legacy_runs(sections):
    i = 0
    while i < len(sections):
        first = sections[i]
        key = first.row_key or ""
        if not key:
            yield [first]
            i += 1
            continue
        run = [first]
        i += 1
        while i < len(sections) and (sections[i].row_key or "") == key:
            run.append(sections[i])
            i += 1
        yield run


def backfill_containers(apps, schema_editor):
    StorefrontPage = apps.get_model("storefront_builder", "StorefrontPage")
    StorefrontSection = apps.get_model("storefront_builder", "StorefrontSection")
    StorefrontContainer = apps.get_model("storefront_builder", "StorefrontContainer")
    StorefrontCell = apps.get_model("storefront_builder", "StorefrontCell")

    for page in StorefrontPage.objects.all().iterator():
        sections = list(
            StorefrontSection.objects.filter(page_id=page.pk).order_by("order", "id")
        )
        container_order = 0
        for run in _legacy_runs(sections):
            spans = tuple(section.row_span if section.row_key else 12 for section in run)
            container = StorefrontContainer.objects.create(
                page_id=page.pk,
                order=container_order,
                stable_id=uuid.uuid4(),
                layout_key=PRESET_BY_SPANS.get(spans, "custom"),
                settings=dict(DEFAULT_SETTINGS),
                is_locked=False,
            )
            StorefrontCell.objects.bulk_create([
                StorefrontCell(
                    container_id=container.pk,
                    order=index,
                    stable_id=uuid.uuid4(),
                    span=span,
                    section_id=section.pk,
                    settings={},
                )
                for index, (section, span) in enumerate(zip(run, spans))
            ])
            container_order += 1


def reverse_backfill(apps, schema_editor):
    # The legacy row_key/row_span fields remain untouched by the forward
    # migration, so dropping the new models is sufficient for a safe reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("storefront_builder", "0013_storefrontedithistoryentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorefrontContainer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")),
                ("stable_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, help_text="در Clone/Restore حفظ می‌شود تا هویت Container بین نسخه‌ها پایدار بماند.", verbose_name="شناسه منطقی پایدار")),
                ("layout_key", models.CharField(default="single", help_text="برچسب Preset رابط کاربری؛ عرض واقعی هر خانه در StorefrontCell.span ذخیره می‌شود.", max_length=32, verbose_name="چینش")),
                ("settings", models.JSONField(blank=True, default=dict, help_text="فاصله ستون‌ها، رفتار موبایل، عرض محتوا و تنظیمات توسعه‌پذیر آینده.", verbose_name="تنظیمات Container")),
                ("is_locked", models.BooleanField(default=False, help_text="قفل Container مستقل از قفل محتوای داخل Cellها است.", verbose_name="قفل‌شده")),
                ("page", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="containers", to="storefront_builder.storefrontpage", verbose_name="صفحه")),
            ],
            options={
                "verbose_name": "کانتینر چیدمان فروشگاه",
                "verbose_name_plural": "کانتینرهای چیدمان فروشگاه",
                "ordering": ["order", "id"],
                "indexes": [models.Index(fields=["page", "order"], name="sfb_container_page_order_idx")],
                "constraints": [models.UniqueConstraint(fields=("page", "stable_id"), name="storefront_container_unique_stable_id_per_page")],
            },
        ),
        migrations.CreateModel(
            name="StorefrontCell",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب خانه")),
                ("stable_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, help_text="در Clone/Restore حفظ می‌شود تا هویت Cell بین نسخه‌ها پایدار بماند.", verbose_name="شناسه منطقی پایدار")),
                ("span", models.PositiveSmallIntegerField(default=12, help_text="عرض واقعی Cell روی گرید ۱۲ واحدی؛ مجموع Cellهای هر Container باید ۱۲ باشد.", verbose_name="عرض دسکتاپ از ۱۲")),
                ("settings", models.JSONField(blank=True, default=dict, help_text="تنظیمات توسعه‌پذیر Cell مانند تراز، رفتار موبایل یا overrideهای آینده.", verbose_name="تنظیمات خانه")),
                ("container", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cells", to="storefront_builder.storefrontcontainer", verbose_name="کانتینر")),
                ("section", models.OneToOneField(blank=True, help_text="خالی بودن مجاز است؛ محتوا بعداً از کتابخانه داخل این Cell قرار می‌گیرد.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="placement_cell", to="storefront_builder.storefrontsection", verbose_name="محتوا")),
            ],
            options={
                "verbose_name": "خانه کانتینر فروشگاه",
                "verbose_name_plural": "خانه‌های کانتینر فروشگاه",
                "ordering": ["order", "id"],
                "indexes": [models.Index(fields=["container", "order"], name="sfb_cell_container_order_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("container", "stable_id"), name="storefront_cell_unique_stable_id_per_container"),
                    models.CheckConstraint(condition=models.Q(span__gte=1, span__lte=12), name="storefront_cell_span_between_1_and_12"),
                ],
            },
        ),
        migrations.RunPython(backfill_containers, reverse_backfill),
    ]
