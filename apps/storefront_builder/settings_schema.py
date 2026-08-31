"""U— R4 Task 3: the declarative Settings Schema core.

A closed, JSON-safe field-type contract for section settings. This is a
Strangler boundary alongside the legacy ``SectionDefinition.validate_settings``
handwritten validators, not a replacement for them: ``clean_schema_patch``
only cleans the subset of keys a schema explicitly declares, and callers are
expected to run the result through the existing legacy validator afterwards
(see the architecture spec, Part V). No field type here allows arbitrary
merchant-controlled HTML/CSS/JS/template execution — ``rich_text`` is a
semantic field type whose actual sanitization remains the existing
sanitizer's job, not this module's.
"""

from __future__ import annotations

import dataclasses
import json

ALLOWED_FIELD_TYPES = frozenset({
    "text",
    "textarea",
    "rich_text",
    "integer",
    "boolean",
    "choice",
    "color",
    "media",
    "variant",
    "resource_source",
    "appearance_override",
})

ALLOWED_GROUPS = frozenset({
    "basic",
    "advanced",
})

_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_digits(value: object) -> str:
    """Persian/Arabic-Indic → ASCII digit normalization, used by every
    server-side integer cleaning path. Server correctness must never depend
    on the browser having normalized digits first."""
    return str(value).translate(_DIGIT_TRANSLATION)


class SettingsSchemaError(ValueError):
    """Raised for schema-construction and patch-cleaning contract failures.

    Subclasses ``ValueError`` so existing ``assertRaises(ValueError, ...)``
    call sites (legacy validators, tests) remain compatible.
    """


@dataclasses.dataclass(frozen=True)
class SettingsField:
    key: str
    label: str
    field_type: str
    group: str
    default: object = None
    required: bool = False
    choices: tuple[tuple[str, str], ...] = ()
    min_value: int | None = None
    max_value: int | None = None
    max_length: int | None = None
    widget_hint: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            raise SettingsSchemaError("Settings field key must not be empty")
        if self.field_type not in ALLOWED_FIELD_TYPES:
            raise SettingsSchemaError(
                f"Unsupported settings field_type {self.field_type!r} for key {self.key!r}"
            )
        if self.group not in ALLOWED_GROUPS:
            raise SettingsSchemaError(
                f"Unsupported settings group {self.group!r} for key {self.key!r}"
            )

        normalized_choices = []
        for pair in self.choices or ():
            pair = tuple(pair)
            if len(pair) != 2:
                raise SettingsSchemaError(
                    f"Malformed choice pair for {self.key!r}: {pair!r} (must be a 2-item pair)"
                )
            value, label = pair
            if not isinstance(value, str) or not isinstance(label, str):
                raise SettingsSchemaError(
                    f"Choice value/label for {self.key!r} must be strings (got {pair!r})"
                )
            normalized_choices.append(pair)
        object.__setattr__(self, "choices", tuple(normalized_choices))

        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise SettingsSchemaError(
                f"min_value {self.min_value} must be <= max_value {self.max_value} for {self.key!r}"
            )

        if self.max_length is not None and self.max_length < 0:
            raise SettingsSchemaError(f"max_length must not be negative for {self.key!r}")

        try:
            json.dumps(self.default)
        except TypeError as exc:
            raise SettingsSchemaError(
                f"default for {self.key!r} is not JSON-safe: {self.default!r}"
            ) from exc


@dataclasses.dataclass(frozen=True)
class SettingsSchema:
    fields: tuple[SettingsField, ...]
    preserve_unmanaged: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields or ()))
        seen_keys: set[str] = set()
        for field in self.fields:
            if not isinstance(field, SettingsField):
                raise SettingsSchemaError(
                    f"SettingsSchema.fields must contain SettingsField instances (got {field!r})"
                )
            if field.key in seen_keys:
                raise SettingsSchemaError(f"Duplicate settings field key {field.key!r}")
            seen_keys.add(field.key)

    def get_field(self, key: str) -> SettingsField | None:
        for field in self.fields:
            if field.key == key:
                return field
        return None


_BOOLEAN_STRING_VALUES = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "on": True,
    "off": False,
}


def _clean_boolean_value(field: SettingsField, raw_value: object) -> bool:
    """Explicit boolean parsing — never Python truthiness. ``bool("false")``
    is ``True`` in Python, which is exactly the kind of surprise this must
    not reproduce for merchant-facing settings."""
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in _BOOLEAN_STRING_VALUES:
            return _BOOLEAN_STRING_VALUES[normalized]
    elif isinstance(raw_value, int):
        if raw_value == 1:
            return True
        if raw_value == 0:
            return False
    raise SettingsSchemaError(
        f"Invalid boolean value for {field.key!r}: {raw_value!r}"
    )


def _clean_field_value(field: SettingsField, raw_value: object) -> object:
    if field.field_type == "integer":
        try:
            cleaned = int(normalize_digits(raw_value))
        except (TypeError, ValueError) as exc:
            raise SettingsSchemaError(
                f"Invalid integer value for {field.key!r}: {raw_value!r}"
            ) from exc
        if field.min_value is not None and cleaned < field.min_value:
            raise SettingsSchemaError(
                f"{field.key!r} must be >= {field.min_value} (got {cleaned})"
            )
        if field.max_value is not None and cleaned > field.max_value:
            raise SettingsSchemaError(
                f"{field.key!r} must be <= {field.max_value} (got {cleaned})"
            )
        return cleaned

    if field.field_type == "boolean":
        return _clean_boolean_value(field, raw_value)

    if field.field_type == "choice":
        allowed_values = {value for value, _label in field.choices}
        if raw_value not in allowed_values:
            raise SettingsSchemaError(
                f"{field.key!r} must be one of {sorted(allowed_values)!r} (got {raw_value!r})"
            )
        return raw_value

    if field.field_type in ("text", "textarea", "rich_text"):
        cleaned = raw_value if isinstance(raw_value, str) else str(raw_value)
        if field.max_length is not None and len(cleaned) > field.max_length:
            raise SettingsSchemaError(
                f"{field.key!r} exceeds max_length {field.max_length} (got {len(cleaned)})"
            )
        return cleaned

    # color / media / variant / resource_source / appearance_override:
    # opaque, schema-declared but not type-coerced in Task 3 — passed
    # through unchanged for the legacy validator to authoritatively check.
    return raw_value


def clean_schema_patch(schema: SettingsSchema, raw_patch: dict, current_settings: dict) -> dict:
    """Clean only the schema-declared keys present in ``raw_patch`` and
    merge them into (a copy of) ``current_settings``. Never mutates either
    input. Unknown keys in ``raw_patch`` are always rejected — regardless
    of ``preserve_unmanaged``, which only governs whether *existing*
    undeclared keys already in ``current_settings`` survive the merge."""
    declared_keys = {field.key for field in schema.fields}
    unknown_keys = set(raw_patch) - declared_keys
    if unknown_keys:
        raise SettingsSchemaError(
            f"Unknown settings key(s): {sorted(unknown_keys)!r}"
        )

    cleaned_patch = {}
    for field in schema.fields:
        if field.key in raw_patch:
            cleaned_patch[field.key] = _clean_field_value(field, raw_patch[field.key])

    if schema.preserve_unmanaged:
        merged = dict(current_settings)
        merged.update(cleaned_patch)
        return merged

    declared_current = {
        key: current_settings[key] for key in declared_keys if key in current_settings
    }
    declared_current.update(cleaned_patch)
    return declared_current


def serialize_schema(schema: SettingsSchema) -> dict:
    """Deterministic, JSON-safe metadata for the Inspector layer. Declared
    field order is preserved; no Python callables or runtime objects are
    included."""
    return {
        "preserve_unmanaged": schema.preserve_unmanaged,
        "fields": [
            {
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "group": field.group,
                "default": field.default,
                "required": field.required,
                "choices": [list(pair) for pair in field.choices],
                "min_value": field.min_value,
                "max_value": field.max_value,
                "max_length": field.max_length,
                "widget_hint": field.widget_hint,
            }
            for field in schema.fields
        ],
    }
