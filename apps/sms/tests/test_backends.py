from unittest.mock import Mock, patch

from django.test import TestCase

from apps.sms.services.backends import ConsoleBackend, MelipayamakBackend


class ConsoleBackendTests(TestCase):
    def test_always_succeeds_without_network_call(self):
        result = ConsoleBackend().send(to="09121234567", text="سلام")
        self.assertTrue(result.success)
        self.assertEqual(result.provider_ref_id, "console")


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
