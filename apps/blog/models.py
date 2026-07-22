from django.db import models

from apps.core.models import TimeStampedModel


class BlogPost(TimeStampedModel):
    title = models.CharField("عنوان", max_length=220)
    slug = models.SlugField("اسلاگ", max_length=240, unique=True, allow_unicode=True)
    category_label = models.CharField("دسته‌ی نمایشی", max_length=80, blank=True)
    cover_emoji = models.CharField("اموجی کاور", max_length=10, blank=True)
    cover_image = models.ImageField("تصویر کاور", upload_to="blog/covers/", null=True, blank=True)
    tint = models.CharField("رنگ پس‌زمینه", max_length=20, blank=True)
    excerpt = models.CharField("خلاصه", max_length=300, blank=True)
    body = models.TextField("متن مطلب")
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)

    class Meta:
        verbose_name = "مطلب وبلاگ"
        verbose_name_plural = "مطالب وبلاگ"
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title
