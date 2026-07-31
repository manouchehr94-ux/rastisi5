"""Section 16 — the in-app notifications list view: only ever shows the
logged-in owner's own IN_APP notifications, and "mark all read" only
touches their own unread rows."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import NotificationOutbox
from apps.notifications.services.notification_service import enqueue

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class NotificationsListViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="09121350011", password="a-very-strong-pass-1")
        self.other = User.objects.create_user(username="09121350022", password="a-very-strong-pass-1")
        self.client.force_login(self.owner)

    def test_shows_only_the_current_users_notifications(self):
        enqueue(channel=NotificationOutbox.Channel.IN_APP, subject="مالِ من", body="b", recipient_user=self.owner)
        enqueue(channel=NotificationOutbox.Channel.IN_APP, subject="مالِ دیگری", body="b", recipient_user=self.other)
        response = self.client.get("/app/notifications/", HTTP_HOST=_HOST)
        self.assertContains(response, "مالِ من")
        self.assertNotContains(response, "مالِ دیگری")

    def test_hides_non_in_app_notifications(self):
        enqueue(channel=NotificationOutbox.Channel.SMS, body="پیامک", recipient_phone="0912", recipient_user=self.owner)
        response = self.client.get("/app/notifications/", HTTP_HOST=_HOST)
        self.assertEqual(len(response.context["notifications"]), 0)

    def test_mark_all_read(self):
        n = enqueue(channel=NotificationOutbox.Channel.IN_APP, subject="s", body="b", recipient_user=self.owner)
        self.client.post("/app/notifications/", HTTP_HOST=_HOST)
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get("/app/notifications/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
