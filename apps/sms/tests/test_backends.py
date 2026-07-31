import logging
from unittest.mock import Mock, patch

from django.test import TestCase

from apps.sms.models import SmsOutboxItem
from apps.sms.services.backends import ConsoleBackend, KavenegarBackend, MelipayamakBackend, SmsRastiBackend
from apps.stores.models import Store


class ConsoleBackendTests(TestCase):
    def test_always_succeeds_without_network_call(self):
        result = ConsoleBackend().send(to="09121234567", text="سلام")
        self.assertTrue(result.success)
        self.assertEqual(result.provider_ref_id, "console")

    def test_does_not_log_message_text_at_info_level_or_above(self):
        """The console backend's logged text can contain an OTP code (the
        default OTP template embeds {otp_code} directly in the SMS body) —
        it must never be emitted at INFO or above, since INFO is the
        production-default DJANGO_LOG_LEVEL and would otherwise leak OTP
        codes into the production console log stream. It may still log at
        DEBUG, for local development visibility."""
        logger_name = "apps.sms.services.backends"
        with self.assertNoLogs(logger_name, level="INFO"):
            ConsoleBackend().send(to="09121234567", text="کد ورود شما: 123456")

        with self.assertLogs(logger_name, level="DEBUG") as captured:
            ConsoleBackend().send(to="09121234567", text="کد ورود شما: 123456")
        self.assertTrue(any("123456" in message for message in captured.output))


class MelipayamakBackendTests(TestCase):
    def setUp(self):
        self.backend = MelipayamakBackend(username="user1", password="pass1", sender="10001")

    def test_missing_credentials_fail_without_network_call(self):
        backend = MelipayamakBackend(username="", password="", sender="")
        with patch("requests.post") as mock_post:
            result = backend.send(to="09121234567", text="سلام")
        mock_post.assert_not_called()
        self.assertFalse(result.success)

    @patch("requests.post")
    def test_successful_response_marks_success_with_ref_id(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"RetStatus": 1, "Value": "123456789"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.backend.send(to="09121234567", text="سلام")

        self.assertTrue(result.success)
        self.assertEqual(result.provider_ref_id, "123456789")
        called_kwargs = mock_post.call_args.kwargs
        self.assertEqual(called_kwargs["json"]["to"], "09121234567")
        self.assertEqual(called_kwargs["json"]["from"], "10001")
        self.assertIn("timeout", called_kwargs)

    @patch("requests.post")
    def test_provider_error_status_marks_failure(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"RetStatus": 35, "StrRetStatus": "موجودی کافی نیست"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.backend.send(to="09121234567", text="سلام")

        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "موجودی کافی نیست")

    @patch("requests.post", side_effect=ConnectionError("network down"))
    def test_network_error_never_raises(self, mock_post):
        result = self.backend.send(to="09121234567", text="سلام")
        self.assertFalse(result.success)
        self.assertIn("network down", result.error_message)


class KavenegarBackendTests(TestCase):
    def setUp(self):
        self.backend = KavenegarBackend(api_key="key1", sender="10001")

    def test_missing_credentials_fail_without_network_call(self):
        backend = KavenegarBackend(api_key="", sender="")
        with patch("requests.post") as mock_post:
            result = backend.send(to="09121234567", text="سلام")
        mock_post.assert_not_called()
        self.assertFalse(result.success)

    @patch("requests.post")
    def test_successful_response_marks_success_with_ref_id(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "return": {"status": 200, "message": "تایید شد"},
            "entries": [{"messageid": 8792343, "status": 1}],
        }
        mock_post.return_value = mock_response

        result = self.backend.send(to="09121234567", text="سلام")

        self.assertTrue(result.success)
        self.assertEqual(result.provider_ref_id, "8792343")
        called_kwargs = mock_post.call_args.kwargs
        self.assertEqual(called_kwargs["data"]["receptor"], "09121234567")
        self.assertEqual(called_kwargs["data"]["sender"], "10001")
        self.assertIn("timeout", called_kwargs)
        self.assertIn("key1", mock_post.call_args.args[0])

    @patch("requests.post")
    def test_non_200_return_status_marks_failure_even_without_exception(self, mock_post):
        """کاوه‌نگار حتیِ خطاها را هم با بدنه‌ی JSON معتبر برمی‌گرداند — صرفِ
        نبودِ Exception (رفتارِ پیاده‌سازیِ مرجعِ sms.zip) کافی نیست؛ باید
        return.status واقعی بررسی شود."""
        mock_response = Mock()
        mock_response.json.return_value = {"return": {"status": 401, "message": "کلید نامعتبر است"}}
        mock_post.return_value = mock_response

        result = self.backend.send(to="09121234567", text="سلام")

        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "کلید نامعتبر است")

    @patch("requests.post", side_effect=ConnectionError("network down"))
    def test_network_error_never_raises(self, mock_post):
        result = self.backend.send(to="09121234567", text="سلام")
        self.assertFalse(result.success)
        self.assertIn("network down", result.error_message)

    def test_network_error_message_never_leaks_api_key_from_url(self):
        """کلیدِ API بخشی از خودِ URL درخواست است — پیامِ requests.exceptions
        معمولاً URL کامل را می‌آورد؛ نباید در پیامِ خطای برگردانده‌شده
        (که در گزارشِ پیامکِ داشبورد نمایش داده می‌شود) دیده شود."""
        secret_url = self.backend.SEND_URL_TEMPLATE.format(api_key="key1")
        with patch("requests.post", side_effect=ConnectionError(f"Max retries exceeded with url: {secret_url}")):
            result = self.backend.send(to="09121234567", text="سلام")
        self.assertFalse(result.success)
        self.assertNotIn("key1", result.error_message)


class SmsRastiBackendTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_missing_device_token_fails_without_creating_outbox_item(self):
        backend = SmsRastiBackend(store=self.store, device_token="")
        result = backend.send(to="09121234567", text="سلام")
        self.assertFalse(result.success)
        self.assertEqual(SmsOutboxItem.objects.count(), 0)

    def test_send_enqueues_pending_item_and_reports_queued_not_delivered(self):
        backend = SmsRastiBackend(store=self.store, device_token="dev-token-1")
        result = backend.send(to="09121234567", text="سلام دنیا")

        self.assertTrue(result.success)
        item = SmsOutboxItem.objects.get(pk=int(result.provider_ref_id))
        self.assertEqual(item.store, self.store)
        self.assertEqual(item.phone, "09121234567")
        self.assertEqual(item.message, "سلام دنیا")
        # صفی شدن به‌معنایِ «ارسال‌شده» نیست — این فقط با poll/ack مشخص می‌شود.
        self.assertEqual(item.status, SmsOutboxItem.Status.PENDING)
