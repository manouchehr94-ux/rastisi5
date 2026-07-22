from django.test import TestCase
from django.utils import timezone

from .models import BlogPost


class BlogModelsTests(TestCase):
    def test_blogpost_creation(self):
        post = BlogPost.objects.create(
            title="راهنمای خرید کالای دیجیتال",
            slug="digital-buying-guide",
            category_label="راهنمای خرید",
            cover_emoji="🛍️",
            tint="#f1ecfd",
            excerpt="چند نکته‌ی کاربردی برای خرید کالای دیجیتال",
            body="متن کامل مطلب...",
            published_at=timezone.now(),
        )
        self.assertEqual(str(post), "راهنمای خرید کالای دیجیتال")
        self.assertIsNotNone(post.created_at)
