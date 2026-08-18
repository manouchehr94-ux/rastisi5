from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.core.context_processors import shop_settings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain
from apps.stores.services import integration_service
from apps.stores.services.enamad_verification_service import (
    EnamadVerificationMetaError,
    parse_enamad_verification_meta_tag,
)


class EnamadMetaParserTests(TestCase):
    def test_accepts_exact_name_content_meta(self):
        meta = parse_enamad_verification_meta_tag(
            '<meta name="enamad-verification" content="token-123">'
        )
        self.assertEqual(meta.name, "enamad-verification")
        self.assertEqual(meta.content, "token-123")

    def test_rejects_script_or_extra_element(self):
        with self.assertRaises(EnamadVerificationMetaError):
            parse_enamad_verification_meta_tag(
                '<meta name="x" content="y"><script>alert(1)</script>'
            )

    def test_rejects_http_equiv_even_if_it_is_a_meta_tag(self):
        with self.assertRaises(EnamadVerificationMetaError):
            parse_enamad_verification_meta_tag(
                '<meta http-equiv="refresh" content="0;url=https://evil.example">'
            )

    def test_rejects_event_or_extra_attributes(self):
        with self.assertRaises(EnamadVerificationMetaError):
            parse_enamad_verification_meta_tag(
                '<meta name="x" content="y" onload="alert(1)">'
            )


@override_settings(ALLOWED_HOSTS=["merchant-meta.example", "testserver"])
class MerchantEnamadMetaRenderingTests(TestCase):
    def setUp(self):
        self.store = Store.objects.create(
            name="Meta Merchant",
            slug="meta-merchant",
            admin_subdomain="meta-merchant",
            status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        ShopSettings.provision_for(self.store)
        StoreDomain.objects.create(
            store=self.store,
            hostname="merchant-meta.example",
            is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        self.meta_tag = (
            '<meta name="enamad-verification" content="merchant-safe-token">'
        )
        integration_service.connect(
            store=self.store,
            provider_code="enamad",
            values={"verification_meta_tag": self.meta_tag, "enamad_code": ""},
            actor=None,
        )

    def _request(self, host, path="/"):
        request = RequestFactory().get(path, HTTP_HOST=host)
        request.store = self.store
        return request

    def test_context_exposes_parsed_meta_on_own_verified_custom_domain(self):
        context = shop_settings(self._request("merchant-meta.example"))
        self.assertEqual(
            context["SHOP_ENAMAD_VERIFICATION_META_NAME"],
            "enamad-verification",
        )
        self.assertEqual(
            context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"],
            "merchant-safe-token",
        )

    def test_platform_owned_store_subdomain_never_gets_merchant_enamad_meta(self):
        with override_settings(
            ALLOWED_HOSTS=["meta-merchant.rastisi.localhost", "testserver"]
        ):
            context = shop_settings(
                self._request("meta-merchant.rastisi.localhost")
            )
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"], "")

    def test_non_home_page_never_gets_verification_meta(self):
        context = shop_settings(
            self._request("merchant-meta.example", "/products/")
        )
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")

    def test_unverified_custom_domain_never_gets_verification_meta(self):
        StoreDomain.objects.filter(hostname="merchant-meta.example").update(
            verification_status=StoreDomain.VerificationStatus.UNVERIFIED,
            verified_at=None,
        )
        with override_settings(
            ALLOWED_HOSTS=["merchant-meta.example", "testserver"]
        ):
            context = shop_settings(self._request("merchant-meta.example"))
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"], "")

    def test_other_stores_verified_domain_never_gets_this_stores_meta(self):
        other_store = Store.objects.create(
            name="Other Merchant",
            slug="other-merchant",
            admin_subdomain="other-merchant",
            status=Store.Status.ACTIVE,
            onboarding_completed_at=timezone.now(),
        )
        ShopSettings.provision_for(other_store)
        StoreDomain.objects.create(
            store=other_store,
            hostname="other-merchant.example",
            is_primary=True,
            domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        # other_store has no eNamad integration connected at all — its own
        # verified custom-domain home page must never show store A's meta.
        request = RequestFactory().get("/", HTTP_HOST="other-merchant.example")
        request.store = other_store
        with override_settings(
            ALLOWED_HOSTS=["other-merchant.example", "testserver"]
        ):
            context = shop_settings(request)
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_NAME"], "")
        self.assertEqual(context["SHOP_ENAMAD_VERIFICATION_META_CONTENT"], "")
        self.assertNotIn("merchant-safe-token", str(context))
