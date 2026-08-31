from django.test import SimpleTestCase

from apps.storefront_builder.section_registry import SectionDefinition
from apps.storefront_builder.settings_schema import (
    SettingsField,
    SettingsSchema,
    SettingsSchemaError,
    clean_schema_patch,
    normalize_digits,
    serialize_schema,
)


class DigitNormalizationTests(SimpleTestCase):
    def test_normalize_digits_converts_persian_digits(self):
        self.assertEqual(normalize_digits("۱۲"), "12")

    def test_normalize_digits_converts_arabic_indic_digits(self):
        self.assertEqual(normalize_digits("١٢"), "12")

    def test_normalize_digits_passes_through_ascii_digits(self):
        self.assertEqual(normalize_digits("12"), "12")


class SettingsFieldAndSchemaContractTests(SimpleTestCase):
    def test_duplicate_field_key_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsSchema(fields=(
                SettingsField("title", "عنوان", "text", "basic"),
                SettingsField("title", "عنوان دوباره", "text", "basic"),
            ))

    def test_invalid_field_type_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "raw_html", "basic")

    def test_invalid_group_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "text", "expert")

    def test_choices_are_normalized_to_immutable_tuple(self):
        field = SettingsField(
            "hero_style", "مدل نمایش", "choice", "basic",
            choices=[("overlay", "overlay"), ("split", "split")],
        )
        self.assertIsInstance(field.choices, tuple)
        self.assertEqual(field.choices, (("overlay", "overlay"), ("split", "split")))

    def test_schema_fields_are_normalized_to_immutable_tuple(self):
        schema = SettingsSchema(fields=[SettingsField("title", "عنوان", "text", "basic")])
        self.assertIsInstance(schema.fields, tuple)


class CleanSchemaPatchTests(SimpleTestCase):
    def test_integer_field_accepts_persian_digits(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        cleaned = clean_schema_patch(schema, {"item_limit": "۱۲"}, {})
        self.assertEqual(cleaned["item_limit"], 12)

    def test_integer_field_accepts_arabic_indic_digits(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        cleaned = clean_schema_patch(schema, {"item_limit": "١٢"}, {})
        self.assertEqual(cleaned["item_limit"], 12)

    def test_unknown_key_is_rejected(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        with self.assertRaisesMessage(ValueError, "Unknown settings key"):
            clean_schema_patch(schema, {"not_allowed": "x"}, {})

    def test_unknown_key_error_is_settings_schema_error(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"not_allowed": "x"}, {})

    def test_patch_preserves_unmanaged_legacy_keys(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        current = {"title": "قدیم", "responsive": {"hide_on_mobile": False}}
        cleaned = clean_schema_patch(schema, {"title": "جدید"}, current)
        self.assertEqual(cleaned["title"], "جدید")
        self.assertEqual(cleaned["responsive"], {"hide_on_mobile": False})

    def test_patch_does_not_mutate_current_settings_or_raw_patch(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic"),
        ))
        current = {"title": "قدیم", "responsive": {"hide_on_mobile": False}}
        raw_patch = {"title": "جدید"}
        clean_schema_patch(schema, raw_patch, current)
        self.assertEqual(current, {"title": "قدیم", "responsive": {"hide_on_mobile": False}})
        self.assertEqual(raw_patch, {"title": "جدید"})

    def test_preserve_unmanaged_false_drops_undeclared_legacy_keys(self):
        schema = SettingsSchema(
            fields=(SettingsField("title", "عنوان", "text", "basic"),),
            preserve_unmanaged=False,
        )
        current = {"title": "قدیم", "responsive": {"hide_on_mobile": False}}
        cleaned = clean_schema_patch(schema, {"title": "جدید"}, current)
        self.assertEqual(cleaned, {"title": "جدید"})

    def test_integer_lower_bound_is_enforced(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"item_limit": 1}, {})

    def test_integer_upper_bound_is_enforced(self):
        schema = SettingsSchema(fields=(
            SettingsField("item_limit", "تعداد", "integer", "basic", min_value=2, max_value=24),
        ))
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"item_limit": 25}, {})

    def test_choice_value_must_be_in_declared_choices(self):
        schema = SettingsSchema(fields=(
            SettingsField(
                "hero_style", "مدل نمایش", "choice", "basic",
                choices=(("overlay", "overlay"), ("split", "split")),
            ),
        ))
        cleaned = clean_schema_patch(schema, {"hero_style": "split"}, {})
        self.assertEqual(cleaned["hero_style"], "split")
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"hero_style": "not_a_choice"}, {})

    def test_text_max_length_is_enforced(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic", max_length=5),
        ))
        cleaned = clean_schema_patch(schema, {"title": "abcde"}, {})
        self.assertEqual(cleaned["title"], "abcde")
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"title": "abcdef"}, {})


class SerializeSchemaTests(SimpleTestCase):
    def test_serialize_schema_is_json_safe_and_preserves_order(self):
        schema = SettingsSchema(fields=(
            SettingsField("title", "عنوان", "text", "basic", default="", max_length=40),
            SettingsField(
                "item_limit", "تعداد", "integer", "advanced",
                default=8, min_value=2, max_value=24,
            ),
        ))
        payload = serialize_schema(schema)

        self.assertEqual(payload["preserve_unmanaged"], True)
        self.assertEqual([f["key"] for f in payload["fields"]], ["title", "item_limit"])

        first = payload["fields"][0]
        self.assertEqual(first["key"], "title")
        self.assertEqual(first["label"], "عنوان")
        self.assertEqual(first["field_type"], "text")
        self.assertEqual(first["group"], "basic")
        self.assertEqual(first["default"], "")
        self.assertEqual(first["required"], False)
        self.assertEqual(first["choices"], [])
        self.assertIsNone(first["min_value"])
        self.assertIsNone(first["max_value"])
        self.assertEqual(first["max_length"], 40)
        self.assertIsNone(first["widget_hint"])

        import json
        json.dumps(payload)


class SectionDefinitionSettingsSchemaCompatibilityTests(SimpleTestCase):
    def test_existing_style_definition_construction_defaults_settings_schema_to_none(self):
        definition = SectionDefinition(
            key="dummy",
            label_fa="آزمایشی",
            icon="icon",
            template_name="dummy.html",
            validate_settings=lambda settings: settings,
            default_settings=lambda: {},
        )
        self.assertIsNone(definition.settings_schema)
