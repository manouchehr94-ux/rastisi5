from django.db import IntegrityError
from django.test import TestCase

from apps.storefront_builder.models import StorefrontLayout, StorefrontLayoutVersion, StorefrontSection
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class StorefrontLayoutModelTests(TestCase):
    def test_provision_for_creates_row(self):
        layout = StorefrontLayout.provision_for(_akhlaghi())
        self.assertTrue(layout.pk)
        self.assertFalse(layout.uses_visual_storefront_layout)

    def test_provision_for_idempotent(self):
        a = StorefrontLayout.provision_for(_akhlaghi())
        b = StorefrontLayout.provision_for(_akhlaghi())
        self.assertEqual(a.pk, b.pk)

    def test_one_layout_per_store(self):
        StorefrontLayout.objects.create(store=_akhlaghi())
        with self.assertRaises(IntegrityError):
            StorefrontLayout.objects.create(store=_akhlaghi())


class StorefrontLayoutVersionModelTests(TestCase):
    def setUp(self):
        self.layout = StorefrontLayout.provision_for(_akhlaghi())

    def test_version_number_unique_per_layout(self):
        StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        with self.assertRaises(IntegrityError):
            StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)

    def test_default_status_draft(self):
        version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        self.assertEqual(version.status, StorefrontLayoutVersion.Status.DRAFT)

    def test_fingerprint_stable_for_same_content(self):
        v1 = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        StorefrontSection.objects.create(version=v1, section_key="hero_banner", order=0, settings={"a": 1})
        fp1 = v1.compute_fingerprint()
        fp2 = v1.compute_fingerprint()
        self.assertEqual(fp1, fp2)

    def test_fingerprint_changes_with_content(self):
        v1 = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        fp_before = v1.compute_fingerprint()
        StorefrontSection.objects.create(version=v1, section_key="hero_banner", order=0)
        fp_after = v1.compute_fingerprint()
        self.assertNotEqual(fp_before, fp_after)

    def test_fingerprint_independent_of_section_insertion_order(self):
        v1 = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)
        StorefrontSection.objects.create(version=v1, section_key="hero_banner", order=0)
        StorefrontSection.objects.create(version=v1, section_key="newest_products", order=1)
        fp1 = v1.compute_fingerprint()

        v2 = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=2)
        StorefrontSection.objects.create(version=v2, section_key="newest_products", order=1)
        StorefrontSection.objects.create(version=v2, section_key="hero_banner", order=0)
        fp2 = v2.compute_fingerprint()
        self.assertEqual(fp1, fp2)


class StorefrontSectionModelTests(TestCase):
    def setUp(self):
        self.layout = StorefrontLayout.provision_for(_akhlaghi())
        self.version = StorefrontLayoutVersion.objects.create(layout=self.layout, version_number=1)

    def test_ordering(self):
        StorefrontSection.objects.create(version=self.version, section_key="b", order=2)
        StorefrontSection.objects.create(version=self.version, section_key="a", order=1)
        keys = list(self.version.sections.values_list("section_key", flat=True))
        self.assertEqual(keys, ["a", "b"])

    def test_settings_default_empty_dict(self):
        section = StorefrontSection.objects.create(version=self.version, section_key="x", order=0)
        self.assertEqual(section.settings, {})

    def test_cascade_delete_with_version(self):
        section = StorefrontSection.objects.create(version=self.version, section_key="x", order=0)
        self.version.delete()
        self.assertFalse(StorefrontSection.objects.filter(pk=section.pk).exists())
