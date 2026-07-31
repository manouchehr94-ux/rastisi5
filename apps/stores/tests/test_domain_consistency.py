from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.domain_consistency_service import check_domain_consistency
from apps.stores.services.platform_code_service import generate_unique_platform_code


def _make_store(**kwargs):
    kwargs.setdefault("name", "Consistency Store")
    kwargs.setdefault("slug", f"consistency-{Store.objects.count()}")
    kwargs.setdefault("status", Store.Status.ACTIVE)
    kwargs.setdefault("platform_code", generate_unique_platform_code())
    return Store.objects.create(**kwargs)


class CheckDomainConsistencyTests(TestCase):
    def test_clean_store_with_trial_domain_has_no_issues(self):
        store = _make_store()
        StoreDomain.objects.create(
            store=store, hostname=f"{store.platform_code}.rastisi.ir", is_primary=True,
            domain_type=StoreDomain.DomainType.GENERATED_TRIAL,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        issues = check_domain_consistency()
        # The pre-seeded Akhlaghi Store (migration 0002) predates the portal
        # and legitimately has no generated_trial domain of its own — that
        # expected warning is unrelated to the Store this test just made.
        issues = [i for i in issues if "Akhlaghi" not in i["message"]]
        self.assertEqual(issues, [])

    def test_store_without_generated_trial_domain_is_a_warning(self):
        _make_store()
        issues = check_domain_consistency()
        warnings = [i for i in issues if i["severity"] == "warning"]
        self.assertTrue(any("generated_trial" in i["message"] for i in warnings))

    def test_active_store_with_only_retired_domains_is_an_error(self):
        store = _make_store()
        # An ACTIVE Store whose only StoreDomain row is retired: no live
        # address left at all — a genuinely broken/dangling state.
        StoreDomain.objects.create(
            store=store, hostname="orphan-retired.example.com", is_primary=False,
            retired_at=timezone.now(),
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        issues = check_domain_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        self.assertTrue(any("دامنه‌ی اصلیِ زنده" in i["message"] for i in errors))

    def test_active_store_with_a_live_primary_alongside_a_retired_domain_is_clean(self):
        store = _make_store()
        StoreDomain.objects.create(
            store=store, hostname="live.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        StoreDomain.objects.create(
            store=store, hostname="retired.example.com", is_primary=False,
            retired_at=timezone.now(),
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        issues = check_domain_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        self.assertEqual(errors, [])

    def test_reserved_label_under_admin_suffix_is_an_error(self):
        store = _make_store()
        StoreDomain.objects.create(
            store=store, hostname="admin.rastisi.ir", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        issues = check_domain_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        self.assertTrue(any("رزروشده" in i["message"] for i in errors))

    def test_public_domain_colliding_with_a_different_stores_admin_host_is_an_error(self):
        store_a = _make_store(slug="store-a-collision", admin_subdomain="collideme")
        store_b = _make_store(slug="store-b-collision")
        StoreDomain.objects.create(
            store=store_b, hostname="collideme.rastisi.ir", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        issues = check_domain_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        self.assertTrue(any("پنل مدیریت" in i["message"] for i in errors))
        self.assertEqual(store_a.admin_subdomain, "collideme")

    def test_store_owning_its_own_admin_host_as_a_storedomain_is_not_flagged(self):
        # A Store's own StoreDomain matching its OWN admin host is not a
        # cross-store collision (colliding_store_id == domain.store_id).
        store = _make_store(admin_subdomain="selfmatch")
        StoreDomain.objects.create(
            store=store, hostname="selfmatch.rastisi.ir", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        issues = check_domain_consistency()
        errors = [i for i in issues if i["severity"] == "error"]
        self.assertFalse(any("پنل مدیریت" in i["message"] for i in errors))


class VerifyDomainConsistencyCommandTests(TestCase):
    def test_command_exits_zero_when_only_the_seeded_akhlaghi_warning_exists(self):
        # The pre-seeded Akhlaghi Store predates the portal and legitimately
        # triggers one warning (no generated_trial domain) — without
        # --strict, a warning-only result must still exit 0.
        out = StringIO()
        call_command("verify_domain_consistency", stdout=out)
        self.assertIn("Akhlaghi", out.getvalue())

    def test_command_raises_on_error_severity_issue(self):
        store = _make_store()
        StoreDomain.objects.create(
            store=store, hostname="orphan.example.com", is_primary=False, retired_at=timezone.now(),
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        with self.assertRaises(CommandError):
            call_command("verify_domain_consistency", stdout=StringIO(), stderr=StringIO())

    def test_strict_flag_raises_on_warning_only(self):
        _make_store()  # active store, no trial domain -> warning only
        with self.assertRaises(CommandError):
            call_command("verify_domain_consistency", "--strict", stdout=StringIO(), stderr=StringIO())

    def test_without_strict_warning_only_does_not_raise(self):
        _make_store()
        out = StringIO()
        call_command("verify_domain_consistency", stdout=out)
        self.assertIn("هشدار", out.getvalue())
