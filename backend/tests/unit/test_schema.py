"""Target schemas as data.

The two things worth pinning here are the ones that decide whether a
user-defined schema is usable at all: whether derived header spellings actually
match a real client export, and whether they ever match something they should
not. A false match silently migrates the wrong column, which is strictly worse
than escalating an unfamiliar header.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemabridge.domain.schema import (
    TargetFieldSpec,
    TargetSchema,
    derive_spellings,
    normalize_header,
)
from schemabridge.domain.target import ValueKind

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"


def _employee_schema(*, curated: bool = False) -> TargetSchema:
    """The employee shape, optionally with the hand-written spellings.

    Without them, this measures what derivation achieves on its own — which is
    what a user gets when they build a schema and do not list any aliases.
    """
    curated_aliases = {
        "fullName": {"empnm", "empname", "employeename", "staffname"},
        "startDate": {"doj", "dateofjoining", "hiredate"},
        "employmentType": {"emptype", "employeetype", "contracttype"},
    }
    fields = [
        TargetFieldSpec(
            name="employeeId", label="Employee ID", kind=ValueKind.IDENTIFIER,
            required=True, is_identity=True,
        ),
        TargetFieldSpec(
            name="fullName", label="Full name", kind=ValueKind.PERSON_NAME, required=True
        ),
        TargetFieldSpec(
            name="workEmail", label="Work email", kind=ValueKind.EMAIL,
            required=True, is_unique=True,
        ),
        TargetFieldSpec(name="startDate", label="Start date", kind=ValueKind.DATE, required=True),
        TargetFieldSpec(
            name="endDate", label="End date", kind=ValueKind.DATE, not_before="startDate"
        ),
        TargetFieldSpec(name="department", label="Department", kind=ValueKind.TEXT),
        TargetFieldSpec(
            name="employmentType", label="Employment type", kind=ValueKind.ENUM,
            enum_values=("full_time", "part_time", "contract", "intern"),
        ),
    ]
    if curated:
        fields = [
            field.model_copy(update={"aliases": frozenset(curated_aliases.get(field.name, set()))})
            for field in fields
        ]
    return TargetSchema(schema_id="sch_test", name="Employee", fields=tuple(fields))


def _headers(name: str) -> list[str]:
    with (SAMPLES / name).open(encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


class TestDerivedSpellingsMatchRealExports:
    """Derivation has to earn its place: a user schema lists no aliases."""

    def test_most_headers_in_the_shipped_fixtures_are_matched(self) -> None:
        schema = _employee_schema()
        headers = _headers("employees-legacy.csv") + _headers("employees-hr-export.csv")

        matched = [h for h in headers if len(schema.fields_for_header(normalize_header(h))) == 1]

        # Nine of thirteen without a single hand-written alias. The rest go to the
        # model, which is affordable; if derivation matched almost nothing, every
        # column would need a model call and blow the per-run budget.
        assert len(matched) >= 9, f"only matched {matched}"

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("emp_id", "employeeId"),
            ("Employee Number", "employeeId"),
            ("email", "workEmail"),
            ("Work Email", "workEmail"),
            ("dept", "department"),
            ("Division", "department"),
            ("Joining Date", "startDate"),
            ("Engagement Type", "employmentType"),
        ],
    )
    def test_specific_real_headers_resolve(self, header: str, expected: str) -> None:
        schema = _employee_schema()
        assert schema.fields_for_header(normalize_header(header)) == (expected,)

    def test_a_header_two_fields_claim_is_ambiguous_not_guessed(self) -> None:
        """A bare "Date" could be either date, so it must not resolve.

        This replaces a hardcoded list of ambiguous headers: ambiguity now falls
        out of two fields claiming the same spelling.
        """
        schema = _employee_schema()
        claimed = schema.fields_for_header(normalize_header("Date"))
        assert set(claimed) == {"startDate", "endDate"}

    def test_curated_aliases_cover_what_derivation_misses(self) -> None:
        """The shipped template keeps its hand-written spellings as well."""
        schema = _employee_schema(curated=True)
        for header, expected in [
            ("emp_nm", "fullName"),
            ("doj", "startDate"),
            ("emp_type", "employmentType"),
        ]:
            assert schema.fields_for_header(normalize_header(header)) == (expected,)


class TestDerivedSpellingsAreConservative:
    """A wrong match migrates the wrong data. Silence is the safer failure."""

    @pytest.mark.parametrize(
        "header",
        [
            "Manager Name",
            "Personal Email",
            "Date of Birth",
            "Cost Centre Ref",
            "Salary",
            "Emergency Contact Name",
            "Last Login Date",
            "Home Address",
            "Manager Emp ID",
            "Spouse Name",
            "Termination Reason",
            "Team Lead Email",
            "Probation End Date",
            "Reports To",
        ],
    )
    def test_an_unrelated_header_matches_nothing(self, header: str) -> None:
        schema = _employee_schema(curated=True)
        assert schema.fields_for_header(normalize_header(header)) == ()

    def test_very_short_spellings_are_discarded(self) -> None:
        """Two characters collide with too much to be a safe signal."""
        assert all(len(spelling) > 2 for spelling in derive_spellings("id", "ID"))


class TestGeneratedJsonSchema:
    def test_required_and_optional_fields_are_distinguished(self) -> None:
        schema = _employee_schema()
        generated = schema.json_schema
        assert set(generated["required"]) == {"employeeId", "fullName", "workEmail", "startDate"}
        # An optional field accepts null; a required one does not.
        assert generated["properties"]["endDate"]["type"] == ["string", "null"]
        assert generated["properties"]["startDate"]["type"] == "string"

    def test_kinds_become_real_constraints(self) -> None:
        properties = _employee_schema().json_schema["properties"]
        assert properties["workEmail"]["format"] == "email"
        assert properties["startDate"]["format"] == "date"
        assert None in properties["employmentType"]["enum"]
        # An identifier stays an opaque string so "000123" keeps its zeros.
        assert properties["employeeId"]["pattern"].startswith("^[A-Za-z0-9]")

    def test_nothing_outside_the_contract_is_accepted(self) -> None:
        assert _employee_schema().json_schema["additionalProperties"] is False


class TestSchemaIntegrity:
    def test_identity_and_unique_fields_are_reported(self) -> None:
        schema = _employee_schema()
        assert schema.identity_field == "employeeId"
        assert schema.unique_fields == ("workEmail",)

    def test_a_schema_may_name_only_one_identity_field(self) -> None:
        with pytest.raises(ValidationError, match="identify a record"):
            TargetSchema(
                schema_id="s",
                name="Two",
                fields=(
                    TargetFieldSpec(name="a", label="A", is_identity=True),
                    TargetFieldSpec(name="b", label="B", is_identity=True),
                ),
            )

    def test_duplicate_field_names_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="Duplicate field name"):
            TargetSchema(
                schema_id="s",
                name="Dup",
                fields=(
                    TargetFieldSpec(name="a", label="A"),
                    TargetFieldSpec(name="a", label="Again"),
                ),
            )

    def test_an_empty_schema_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one field"):
            TargetSchema(schema_id="s", name="Empty", fields=())

    def test_an_enum_field_must_list_its_values(self) -> None:
        with pytest.raises(ValidationError, match="lists no permitted values"):
            TargetFieldSpec(name="tier", label="Tier", kind=ValueKind.ENUM)

    def test_ordering_against_an_unknown_field_is_refused(self) -> None:
        """A date pair naming a field that does not exist is a typo, not a rule."""
        with pytest.raises(ValidationError, match="does not define"):
            TargetSchema(
                schema_id="s",
                name="Bad pair",
                fields=(TargetFieldSpec(name="ends", label="Ends", not_before="begins"),),
            )

    @pytest.mark.parametrize("name", ["9lives", "has space", "has-dash", "", "a" * 65])
    def test_a_field_name_must_be_usable_as_a_key(self, name: str) -> None:
        with pytest.raises(ValidationError):
            TargetFieldSpec(name=name, label="X")


class TestACompletelyDifferentSchema:
    """Nothing about the engine may assume employees."""

    def test_an_unrelated_shape_is_valid_and_matches_its_own_headers(self) -> None:
        schema = TargetSchema(
            schema_id="sch_orders",
            name="Order",
            fields=(
                TargetFieldSpec(
                    name="orderId", label="Order ID", kind=ValueKind.IDENTIFIER,
                    required=True, is_identity=True,
                ),
                TargetFieldSpec(
                    name="customerEmail", label="Customer email", kind=ValueKind.EMAIL,
                    required=True,
                ),
                TargetFieldSpec(
                    name="status", label="Status", kind=ValueKind.ENUM,
                    enum_values=("open", "shipped", "cancelled"),
                ),
            ),
        )
        assert schema.identity_field == "orderId"
        assert schema.fields_for_header(normalize_header("Order Number")) == ("orderId",)
        assert schema.fields_for_header(normalize_header("Customer Mail")) == ("customerEmail",)
        assert set(schema.json_schema["required"]) == {"orderId", "customerEmail"}
