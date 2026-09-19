"""Validation runs at most twice, then escalates."""

from __future__ import annotations

from schemabridge.domain import validate as validate_module
from schemabridge.domain.cleanup import SourceValues
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.domain.validate import TwoPassResult, ValidationOutcome


def validate_employee(values: SourceValues) -> ValidationOutcome:
    """Validate against the built-in template.

    These tests are about the employee contract specifically, so the schema is
    bound once here rather than repeated at every call. `test_schema.py` covers
    validation against other schemas.
    """
    return validate_module.validate_record(values, schema=BUILTIN_SCHEMA)


def run_validation_passes(values: SourceValues) -> TwoPassResult:
    return validate_module.run_validation_passes(values, schema=BUILTIN_SCHEMA)


VALID = {
    "employeeId": "E-1001",
    "fullName": "Priya Sharma",
    "workEmail": "priya@example.com",
    "startDate": "2026-01-15",
}


class TestValidateEmployee:
    def test_accepts_a_minimal_valid_record(self) -> None:
        assert validate_employee(VALID).valid

    def test_reports_each_missing_required_field(self) -> None:
        result = validate_employee({"employeeId": "E-1"})
        assert not result.valid
        fields = {e.field_name for e in result.errors}
        assert {"fullName", "workEmail", "startDate"} <= fields

    def test_rejects_a_malformed_email(self) -> None:
        result = validate_employee({**VALID, "workEmail": "not-an-email"})
        assert not result.valid
        assert any(e.field_name == "workEmail" for e in result.errors)

    def test_rejects_a_non_iso_date(self) -> None:
        assert not validate_employee({**VALID, "startDate": "03/04/2026"}).valid

    def test_accepts_an_absent_end_date(self) -> None:
        assert validate_employee({**VALID, "endDate": None}).valid

    def test_rejects_an_end_date_before_the_start_date(self) -> None:
        result = validate_employee({**VALID, "startDate": "2026-05-01", "endDate": "2026-04-01"})
        assert not result.valid
        assert any(e.code == "end_before_start" for e in result.errors)

    def test_rejects_an_unknown_employment_type(self) -> None:
        assert not validate_employee({**VALID, "employmentType": "seasonal"}).valid

    def test_rejects_unexpected_extra_fields(self) -> None:
        assert not validate_employee({**VALID, "salary": "50000"}).valid


class TestRunValidationPasses:
    def test_clean_data_passes_on_the_first_attempt(self) -> None:
        result = run_validation_passes(dict(VALID))
        assert result.valid
        assert len(result.passes) == 1
        assert result.passes[0].label == "as_mapped"
        assert result.repairs == ()

    def test_repairs_once_then_revalidates(self) -> None:
        result = run_validation_passes(
            {
                "employeeId": " E-1001 ",
                "fullName": " Priya Sharma ",
                "workEmail": " Priya@EXAMPLE.com ",
                "startDate": "14 March 2026",
            }
        )
        assert len(result.passes) == 2
        assert not result.passes[0].valid
        assert result.passes[1].label == "after_repair"
        assert result.valid
        assert result.values["startDate"] == "2026-03-14"

    def test_stops_after_exactly_two_evaluations_and_reports_both(self) -> None:
        result = run_validation_passes(
            {
                "employeeId": "E-1002",
                "fullName": "Rahul Verma",
                "workEmail": "rahul@@example..com",
                "startDate": "2026-02-01",
            }
        )
        assert len(result.passes) == 2
        assert not result.valid
        assert result.failed_twice
        assert result.passes[0].errors
        assert result.passes[1].errors

    def test_says_plainly_when_no_safe_repair_existed(self) -> None:
        result = run_validation_passes(
            {
                "employeeId": "E-1003",
                "fullName": "Sara Khan",
                "workEmail": "sara@example.com",
                "startDate": "03/04/2026",
            }
        )
        assert result.failed_twice
        # An ambiguous date has no safe automatic repair.
        assert result.repairs == ()
        assert result.no_repair_available

    def test_never_runs_a_third_evaluation(self) -> None:
        result = run_validation_passes({"employeeId": ""})
        assert len(result.passes) <= 2


class TestEmailSyntax:
    """The schema's own format check is too permissive to rely on."""

    def test_rejects_doubled_at_sign(self) -> None:
        assert not validate_employee({**VALID, "workEmail": "rahul@@example..com"}).valid

    def test_rejects_consecutive_dots_in_domain(self) -> None:
        assert not validate_employee({**VALID, "workEmail": "a.b@example..com"}).valid

    def test_rejects_domain_without_a_dot(self) -> None:
        assert not validate_employee({**VALID, "workEmail": "someone@localhost"}).valid

    def test_rejects_trailing_dot_in_local_part(self) -> None:
        assert not validate_employee({**VALID, "workEmail": "someone.@example.com"}).valid

    def test_accepts_ordinary_addresses(self) -> None:
        for good in (
            "priya.sharma@example.com",
            "o'brien@example.co.uk",
            "first+tag@sub.example.org",
            "x_y-z@example-corp.com",
        ):
            assert validate_employee({**VALID, "workEmail": good}).valid, good
