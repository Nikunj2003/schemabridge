"""Safe repairs may not change what a value means."""

from __future__ import annotations

from schemabridge.domain import cleanup as cleanup_module
from schemabridge.domain.cleanup import RepairResult, SourceValues
from schemabridge.domain.target import BUILTIN_SCHEMA, TargetField


def apply_safe_repairs(values: SourceValues) -> RepairResult:
    """Repair against the built-in template, which these cases are about."""
    return cleanup_module.apply_safe_repairs(values, schema=BUILTIN_SCHEMA)


def normalize_enum_value(field_name: str, value: str) -> str | None:
    return cleanup_module.normalize_enum_value(field_name, value, schema=BUILTIN_SCHEMA)


class TestApplySafeRepairs:
    def test_trims_surrounding_but_not_internal_whitespace(self) -> None:
        result = apply_safe_repairs({"fullName": "  Priya   Sharma  "})
        assert result.values["fullName"] == "Priya   Sharma"
        assert any(r.rule == "trim_whitespace" for r in result.repairs)

    def test_preserves_the_casing_the_client_recorded(self) -> None:
        # Title-casing corrupts "McDonald", "van der Berg" and "d'Souza".
        result = apply_safe_repairs({"fullName": "nikunj KHITHA"})
        assert result.values["fullName"] == "nikunj KHITHA"

    def test_keeps_identifiers_opaque_including_leading_zeros(self) -> None:
        result = apply_safe_repairs({"employeeId": " 000123 "})
        assert result.values["employeeId"] == "000123"

    def test_lowercases_only_the_email_domain(self) -> None:
        result = apply_safe_repairs({"workEmail": " John.Smith@EXAMPLE.COM "})
        assert result.values["workEmail"] == "John.Smith@example.com"

    def test_converts_an_unambiguous_date_to_iso(self) -> None:
        result = apply_safe_repairs({"startDate": "14 March 2026"})
        assert result.values["startDate"] == "2026-03-14"
        assert any(r.rule == "normalize_date" for r in result.repairs)

    def test_leaves_an_ambiguous_date_untouched(self) -> None:
        result = apply_safe_repairs({"startDate": "03/04/2026"})
        assert result.values["startDate"] == "03/04/2026"
        assert not any(r.field_name == "startDate" for r in result.repairs)
        assert "startDate" in result.unrepairable

    def test_canonicalises_known_enum_spellings(self) -> None:
        assert (
            apply_safe_repairs({"employmentType": "Full Time"}).values["employmentType"]
            == "full_time"
        )
        assert (
            apply_safe_repairs({"employmentType": "FULL-TIME"}).values["employmentType"]
            == "full_time"
        )
        assert (
            apply_safe_repairs({"employmentType": "Permanent"}).values["employmentType"]
            == "full_time"
        )

    def test_leaves_an_unknown_enum_spelling_alone(self) -> None:
        # Deciding that "Seasonal Temp" means "contract" is a business call.
        result = apply_safe_repairs({"employmentType": "Seasonal Temp"})
        assert result.values["employmentType"] == "Seasonal Temp"
        assert "employmentType" in result.unrepairable

    def test_is_idempotent(self) -> None:
        once = apply_safe_repairs({"fullName": " A  B ", "startDate": "14 March 2026"})
        twice = apply_safe_repairs(once.values)
        assert twice.values == once.values
        assert twice.repairs == ()

    def test_never_invents_a_missing_value(self) -> None:
        result = apply_safe_repairs({"employeeId": "E-1", "department": ""})
        assert result.values["department"] == ""
        assert "startDate" not in result.values


class TestNormalizeEnumValue:
    def test_accepts_canonical_values_unchanged(self) -> None:
        assert normalize_enum_value(TargetField.EMPLOYMENT_TYPE, "contract") == "contract"

    def test_returns_none_outside_the_vocabulary(self) -> None:
        assert normalize_enum_value(TargetField.EMPLOYMENT_TYPE, "zzz") is None
