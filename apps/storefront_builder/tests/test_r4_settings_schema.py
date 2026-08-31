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


# ------------------------------------------------------------------------
# Corrective review pass (post-acf7a48)
# ------------------------------------------------------------------------


class PreserveUnmanagedFalseRetainsDeclaredCurrentValuesTests(SimpleTestCase):
    def test_partial_patch_retains_other_declared_current_values_and_drops_unmanaged(self):
        schema = SettingsSchema(
            fields=(
                SettingsField("title", "عنوان", "text", "basic"),
                SettingsField("subtitle", "زیرعنوان", "text", "basic"),
            ),
            preserve_unmanaged=False,
        )
        current = {
            "title": "old title",
            "subtitle": "old subtitle",
            "responsive": {"hide_on_mobile": False},
        }
        cleaned = clean_schema_patch(schema, {"title": "new title"}, current)
        self.assertEqual(cleaned, {"title": "new title", "subtitle": "old subtitle"})

    def test_partial_patch_with_preserve_unmanaged_false_does_not_mutate_inputs(self):
        schema = SettingsSchema(
            fields=(
                SettingsField("title", "عنوان", "text", "basic"),
                SettingsField("subtitle", "زیرعنوان", "text", "basic"),
            ),
            preserve_unmanaged=False,
        )
        current = {
            "title": "old title",
            "subtitle": "old subtitle",
            "responsive": {"hide_on_mobile": False},
        }
        raw_patch = {"title": "new title"}
        clean_schema_patch(schema, raw_patch, current)
        self.assertEqual(current, {
            "title": "old title",
            "subtitle": "old subtitle",
            "responsive": {"hide_on_mobile": False},
        })
        self.assertEqual(raw_patch, {"title": "new title"})


class BooleanCleaningTests(SimpleTestCase):
    def _schema(self):
        return SettingsSchema(fields=(
            SettingsField("autoplay", "پخش خودکار", "boolean", "basic"),
        ))

    def test_python_booleans_pass_through(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": True}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": False}, {})["autoplay"], False)

    def test_string_true_false_case_insensitive_and_trimmed(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": "true"}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "  TRUE  "}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "false"}, {})["autoplay"], False)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "  FALSE  "}, {})["autoplay"], False)

    def test_string_1_0_on_off(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": "1"}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "0"}, {})["autoplay"], False)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "on"}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": "off"}, {})["autoplay"], False)

    def test_integer_1_0(self):
        schema = self._schema()
        self.assertIs(clean_schema_patch(schema, {"autoplay": 1}, {})["autoplay"], True)
        self.assertIs(clean_schema_patch(schema, {"autoplay": 0}, {})["autoplay"], False)

    def test_ambiguous_string_values_are_rejected(self):
        schema = self._schema()
        for value in ("yes", "no", "anything"):
            with self.assertRaises(SettingsSchemaError):
                clean_schema_patch(schema, {"autoplay": value}, {})

    def test_ambiguous_integer_values_are_rejected(self):
        schema = self._schema()
        for value in (2, -1):
            with self.assertRaises(SettingsSchemaError):
                clean_schema_patch(schema, {"autoplay": value}, {})

    def test_none_is_rejected(self):
        schema = self._schema()
        with self.assertRaises(SettingsSchemaError):
            clean_schema_patch(schema, {"autoplay": None}, {})


class MalformedSchemaDefinitionTests(SimpleTestCase):
    def test_empty_field_key_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("", "عنوان", "text", "basic")

    def test_malformed_choice_pair_is_rejected_at_field_construction(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "hero_style", "مدل نمایش", "choice", "basic",
                choices=(("overlay",),),
            )

    def test_choice_values_and_labels_must_be_strings(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "item_limit", "تعداد", "choice", "basic",
                choices=((1, "one"),),
            )
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "item_limit", "تعداد", "choice", "basic",
                choices=(("one", 1),),
            )

    def test_incoherent_integer_bounds_are_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField(
                "item_limit", "تعداد", "integer", "basic",
                min_value=10, max_value=2,
            )

    def test_negative_max_length_is_rejected(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "text", "basic", max_length=-1)

    def test_schema_fields_must_be_settings_field_instances(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsSchema(fields=("not-a-settings-field",))


class JsonSafeDefaultTests(SimpleTestCase):
    def test_non_json_safe_default_is_rejected_at_field_construction(self):
        with self.assertRaises(SettingsSchemaError):
            SettingsField("title", "عنوان", "text", "basic", default=object())

    def test_json_compatible_primitive_defaults_are_accepted(self):
        SettingsField("title", "عنوان", "text", "basic", default="")
        SettingsField("item_limit", "تعداد", "integer", "basic", default=8)
        SettingsField("autoplay", "پخش خودکار", "boolean", "basic", default=True)
        SettingsField("tags", "برچسب‌ها", "text", "basic", default=["a", "b"])
        SettingsField("meta", "متا", "text", "basic", default={"a": 1})
