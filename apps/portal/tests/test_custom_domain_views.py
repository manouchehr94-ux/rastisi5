"""Section 12 — the owner-facing custom domain views: add → begin DNS
verification → check (mocked DNS) → activate (step-up gated, like billing
purchase and handle claim)."""

from unittest.mock import patch

import dns.resolver
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.models import OwnerProfile
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.stores.services.domain_verification_service import verification_record_name

User = get_user_model()
_HOST = "rastisi.localhost"


class _FakeTXTRecord:
    def __init__(self, *chunks):
        self.strings = [chunk.encode() for chunk in chunks]


def _resolve_target():
    return "apps.stores.services.domain_verification_service.dns.resolver.resolve"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class CustomDomainViewsTestCase(TestCase):
    def setUp(self):
        cache.clear()  # OTP rate-limit counters are cache-backed and leak across tests otherwise
        self.store = Store.objects.create(
            name="فروشگاه دامنه ویو", slug="domain-view-store", admin_subdomain="domain-view-store",
        )
        self.owner = User.objects.create_user(username="09121290011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121290011", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(self.owner)
        self.code = "998877"
        import apps.portal.services.owner_otp_service as svc
        self._original_generate_code = svc._generate_code
        svc._generate_code = lambda: self.code
        self.addCleanup(self._restore)

    def _restore(self):
        import apps.portal.services.owner_otp_service as svc
        svc._generate_code = self._original_generate_code

    def _list_url(self):
        return f"/app/stores/{self.store.public_id}/domains/"


class AddDomainViewTests(CustomDomainViewsTestCase):
    def test_add_creates_unverified_domain(self):
        response = self.client.post(self._list_url(), {"action": "add", "hostname": "shop.example.com"}, HTTP_HOST=_HOST)
        self.assertRedirects(response, self._list_url())
        self.assertTrue(
            StoreDomain.objects.filter(store=self.store, hostname="shop.example.com", domain_type="custom_domain").exists()
        )

    def test_list_shows_added_domain(self):
        self.client.post(self._list_url(), {"action": "add", "hostname": "shop.example.com"}, HTTP_HOST=_HOST)
        response = self.client.get(self._list_url(), HTTP_HOST=_HOST)
        self.assertContains(response, "shop.example.com")

    def test_rejects_rastisi_subdomain(self):
        response = self.client.post(
            self._list_url(), {"action": "add", "hostname": "evil.rastisi.ir"}, HTTP_HOST=_HOST, follow=True,
        )
        self.assertFalse(StoreDomain.objects.filter(hostname="evil.rastisi.ir").exists())

    def test_other_owner_cannot_see_someone_elses_domains(self):
        other = User.objects.create_user(username="09121290022", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.get(self._list_url(), HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)

    def test_adding_a_likely_typo_of_an_existing_domain_shows_a_warning(self):
        self.client.post(self._list_url(), {"action": "add", "hostname": "digigol.ir"}, HTTP_HOST=_HOST)
        response = self.client.post(
            self._list_url(), {"action": "add", "hostname": "digigole.ir"}, HTTP_HOST=_HOST, follow=True,
        )
        self.assertContains(response, "digigol.ir")
        self.assertContains(response, "p-alert-warning")

    def test_adding_a_clean_new_domain_shows_no_typo_warning(self):
        response = self.client.post(
            self._list_url(), {"action": "add", "hostname": "brand-new-shop.ir"}, HTTP_HOST=_HOST, follow=True,
        )
        self.assertNotContains(response, "p-alert-warning")

    def test_hostname_is_never_auto_corrected(self):
        """درخواستِ typo-suggestion هرگز مقدارِ واردشده را جایگزین نمی‌کند —
        دقیقاً همان چیزی که کاربر تایپ کرده ذخیره می‌شود."""
        self.client.post(self._list_url(), {"action": "add", "hostname": "digigol.ir"}, HTTP_HOST=_HOST)
        self.client.post(self._list_url(), {"action": "add", "hostname": "digigole.ir"}, HTTP_HOST=_HOST)
        self.assertTrue(StoreDomain.objects.filter(store=self.store, hostname="digigole.ir").exists())


class BeginAndCheckVerificationViewTests(CustomDomainViewsTestCase):
    def _add_domain(self):
        self.client.post(self._list_url(), {"action": "add", "hostname": "shop.example.com"}, HTTP_HOST=_HOST)
        return StoreDomain.objects.get(store=self.store, hostname="shop.example.com")

    def test_begin_verify_shows_txt_instructions(self):
        domain = self._add_domain()
        self.client.post(
            f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST,
        )
        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.PENDING)
        response = self.client.get(self._list_url(), HTTP_HOST=_HOST)
        self.assertContains(response, verification_record_name(domain.hostname))

    def test_check_with_matching_dns_verifies(self):
        domain = self._add_domain()
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST)
        domain.refresh_from_db()

        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={domain.verification_token}")]
            self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/check/", HTTP_HOST=_HOST)

        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.VERIFIED)

    def test_check_with_no_dns_record_stays_pending(self):
        domain = self._add_domain()
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST)

        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.side_effect = dns.resolver.NXDOMAIN()
            self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/check/", HTTP_HOST=_HOST)

        domain.refresh_from_db()
        self.assertEqual(domain.verification_status, StoreDomain.VerificationStatus.PENDING)


class ActivateDomainViewTests(CustomDomainViewsTestCase):
    def _verified_domain(self):
        self.client.post(self._list_url(), {"action": "add", "hostname": "shop.example.com"}, HTTP_HOST=_HOST)
        domain = StoreDomain.objects.get(store=self.store, hostname="shop.example.com")
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST)
        domain.refresh_from_db()
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={domain.verification_token}")]
            self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/check/", HTTP_HOST=_HOST)
        domain.refresh_from_db()
        return domain

    def test_activation_is_gated_behind_step_up_by_default(self):
        domain = self._verified_domain()
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/domains/{domain.pk}/activate/", HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/domains/activate/step-up/")
        domain.refresh_from_db()
        self.assertFalse(domain.is_primary)

    def test_correct_step_up_code_activates_the_domain(self):
        domain = self._verified_domain()
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/activate/", HTTP_HOST=_HOST)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/domains/activate/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, self._list_url())
        domain.refresh_from_db()
        self.assertTrue(domain.is_primary)

    def test_cannot_activate_an_unverified_domain(self):
        self.client.post(self._list_url(), {"action": "add", "hostname": "unverified.example.com"}, HTTP_HOST=_HOST)
        domain = StoreDomain.objects.get(store=self.store, hostname="unverified.example.com")
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/activate/", HTTP_HOST=_HOST)
        self.client.post(
            f"/app/stores/{self.store.public_id}/domains/activate/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        domain.refresh_from_db()
        self.assertFalse(domain.is_primary)


class FinalCheckViewTests(CustomDomainViewsTestCase):
    """تستِ نهاییِ اتصال (SSL) — صرفاً تشخیصی، هرگز چیزی را در دیتابیس
    تغییر نمی‌دهد یا فعال‌سازی را انجام نمی‌دهد."""

    def _verified_domain(self):
        self.client.post(self._list_url(), {"action": "add", "hostname": "shop.example.com"}, HTTP_HOST=_HOST)
        domain = StoreDomain.objects.get(store=self.store, hostname="shop.example.com")
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST)
        domain.refresh_from_db()
        with patch(_resolve_target()) as mock_resolve:
            mock_resolve.return_value = [_FakeTXTRecord(f"rastisi-verify={domain.verification_token}")]
            self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/check/", HTTP_HOST=_HOST)
        domain.refresh_from_db()
        return domain

    def test_reachable_ssl_shows_success_message(self):
        from apps.stores.services.domain_verification_service import SslConnectionCheck

        domain = self._verified_domain()
        with patch(
            "apps.portal.views.domain_verification_service.check_ssl_connection",
            return_value=SslConnectionCheck(reachable=True, certificate_expires_at=None, error=""),
        ):
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/final-check/",
                HTTP_HOST=_HOST, follow=True,
            )
        self.assertContains(response, "با موفقیت برقرار شد")

    def test_unreachable_ssl_shows_warning_message_and_does_not_activate(self):
        from apps.stores.services.domain_verification_service import SslConnectionCheck

        domain = self._verified_domain()
        with patch(
            "apps.portal.views.domain_verification_service.check_ssl_connection",
            return_value=SslConnectionCheck(reachable=False, certificate_expires_at=None, error="timed out"),
        ):
            response = self.client.post(
                f"/app/stores/{self.store.public_id}/domains/{domain.pk}/final-check/",
                HTTP_HOST=_HOST, follow=True,
            )
        self.assertContains(response, "هنوز برقرار نیست")
        domain.refresh_from_db()
        self.assertFalse(domain.is_primary)

    def test_other_owner_cannot_final_check_someone_elses_domain(self):
        domain = self._verified_domain()
        other = User.objects.create_user(username="09121290033", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/domains/{domain.pk}/final-check/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)
