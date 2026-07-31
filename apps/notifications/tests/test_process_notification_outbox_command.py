from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.notifications.models import NotificationOutbox
from apps.notifications.services.notification_service import enqueue


class ProcessNotificationOutboxCommandTests(TestCase):
    def test_processes_pending_notifications_and_reports_counts(self):
        enqueue(channel=NotificationOutbox.Channel.IN_APP, body="متن")
        out = StringIO()
        call_command("process_notification_outbox", stdout=out)
        self.assertIn("1 اعلان پردازش شد", out.getvalue())
        self.assertIn("1 ارسال‌شده", out.getvalue())

    def test_respects_limit(self):
        for _ in range(3):
            enqueue(channel=NotificationOutbox.Channel.IN_APP, body="متن")
        out = StringIO()
        call_command("process_notification_outbox", "--limit=1", stdout=out)
        self.assertEqual(NotificationOutbox.objects.filter(status=NotificationOutbox.Status.SENT).count(), 1)
