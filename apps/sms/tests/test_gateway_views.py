from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.sms.models import SmsOutboxItem
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SmsRastiPollTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        shop = ShopSettings.load(store=self.store)
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()

    def test_missing_or_wrong_token_is_unauthorized(self):
        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "wrong-token"})
        self.assertEqual(response.status_code, 401)

        response = self.client.get(reverse("sms:smsrasti-poll"))
        self.assertEqual(response.status_code, 401)

    def test_empty_queue_reports_empty(self):
        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "dev-token-1"})
        self.assertEqual(response.json()["status"], "empty")

    def test_claims_oldest_pending_item_and_marks_sending_not_sent(self):
        """poll هرگز نباید صرفِ claim را «ارسال‌شده» علامت بزند — این باگِ
        نسخه‌ی مرجعِ gateway_api.py بود؛ باید فقط sending شود."""
        item = SmsOutboxItem.objects.create(store=self.store, phone="09121234567", message="سلام")

        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "dev-token-1"})
        data = response.json()

        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["id"], item.pk)
        self.assertEqual(data["phone"], "09121234567")
        item.refresh_from_db()
        self.assertEqual(item.status, SmsOutboxItem.Status.SENDING)
        self.assertIsNotNone(item.claimed_at)
        self.assertEqual(item.attempt_count, 1)

    def test_already_claimed_item_is_not_claimed_again_before_reclaim_window(self):
        SmsOutboxItem.objects.create(
            store=self.store, phone="09121234567", message="سلام",
            status=SmsOutboxItem.Status.SENDING, claimed_at=timezone.now(),
        )
        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "dev-token-1"})
        self.assertEqual(response.json()["status"], "empty")

    def test_stale_claimed_item_is_reclaimable(self):
        """اگر گیت‌وی claim کند اما هرگز ack نفرستد (کرش/قطعیِ شبکه)، پس از
        بازه‌ی reclaim دوباره قابلِ claim است — برای همیشه گیر نمی‌کند."""
        stale_time = timezone.now() - timedelta(seconds=999)
        item = SmsOutboxItem.objects.create(
            store=self.store, phone="09121234567", message="سلام",
            status=SmsOutboxItem.Status.SENDING, claimed_at=stale_time, attempt_count=1,
        )
        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "dev-token-1"})
        data = response.json()
        self.assertEqual(data["status"], "ok")
        item.refresh_from_db()
        self.assertEqual(item.attempt_count, 2)

    def test_oldest_item_claimed_first(self):
        older = SmsOutboxItem.objects.create(store=self.store, phone="09121111111", message="اول")
        SmsOutboxItem.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(minutes=5))
        SmsOutboxItem.objects.create(store=self.store, phone="09122222222", message="دوم")

        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "dev-token-1"})
        self.assertEqual(response.json()["id"], older.pk)

    def test_cannot_claim_another_stores_queued_item(self):
        other_store = Store.objects.create(name="Store B", slug="store-b-gw", status=Store.Status.ACTIVE)
        other_shop = ShopSettings.provision_for(other_store)
        other_shop.smsrasti_device_token = "dev-token-2"
        other_shop.save()
        SmsOutboxItem.objects.create(store=other_store, phone="09121234567", message="متعلق به فروشگاه دیگر")

        response = self.client.get(reverse("sms:smsrasti-poll"), {"token": "dev-token-1"})
        self.assertEqual(response.json()["status"], "empty")


class SmsRastiAckTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        shop = ShopSettings.load(store=self.store)
        shop.smsrasti_device_token = "dev-token-1"
        shop.save()
        self.item = SmsOutboxItem.objects.create(
            store=self.store, phone="09121234567", message="سلام",
            status=SmsOutboxItem.Status.SENDING, claimed_at=timezone.now(),
        )

    def test_missing_or_wrong_token_is_unauthorized(self):
        response = self.client.post(reverse("sms:smsrasti-ack"), {"token": "wrong", "id": self.item.pk})
        self.assertEqual(response.status_code, 401)

    def test_ack_sent_marks_item_sent_with_ref_id(self):
        response = self.client.post(reverse("sms:smsrasti-ack"), {
            "token": "dev-token-1", "id": self.item.pk, "status": "sent", "rec_id": "device-msg-42",
        })
        self.assertEqual(response.json()["status"], "ok")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, SmsOutboxItem.Status.SENT)
        self.assertEqual(self.item.provider_ref_id, "device-msg-42")
        self.assertIsNotNone(self.item.sent_at)

    def test_ack_failed_marks_item_failed_with_error(self):
        response = self.client.post(reverse("sms:smsrasti-ack"), {
            "token": "dev-token-1", "id": self.item.pk, "status": "failed", "error": "no signal",
        })
        self.assertEqual(response.json()["status"], "ok")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, SmsOutboxItem.Status.FAILED)
        self.assertEqual(self.item.error_message, "no signal")

    def test_unknown_item_id_is_not_found(self):
        response = self.client.post(reverse("sms:smsrasti-ack"), {
            "token": "dev-token-1", "id": 999999, "status": "sent",
        })
        self.assertEqual(response.status_code, 404)

    def test_cannot_ack_another_stores_item(self):
        other_store = Store.objects.create(name="Store C", slug="store-c-gw", status=Store.Status.ACTIVE)
        other_shop = ShopSettings.provision_for(other_store)
        other_shop.smsrasti_device_token = "dev-token-2"
        other_shop.save()

        response = self.client.post(reverse("sms:smsrasti-ack"), {
            "token": "dev-token-2", "id": self.item.pk, "status": "sent",
        })
        self.assertEqual(response.status_code, 404)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, SmsOutboxItem.Status.SENDING)
