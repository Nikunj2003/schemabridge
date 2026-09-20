"""A schema nobody wrote code for behaves like the built-in one.

The built-in Employee template is pinned by `test_fixtures.py`. These cases ask
the harder question: does the engine work on a contract it has never seen? Every
piece of behaviour the shipped demo relies on — merging, uniqueness, safe repairs,
ambiguity, required-field escalation, delivery payloads — is exercised here
against an unrelated schema built in the test itself.

The schema below is deliberately nothing to do with employment, so a rule that
secretly keys off "employeeId" or "workEmail" fails rather than passing by luck.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from schemabridge.domain.cleanup import apply_safe_repairs, normalize_enum_value
from schemabridge.domain.identity import IncomingRow, reconcile_identities
from schemabridge.domain.mapping import decide_mappings
from schemabridge.domain.models import (
    ColumnProfile,
    IssueType,
    MappingOutcome,
    Provenance,
    SourceColumn,
)
from schemabridge.domain.normalize import detect_value_kinds, normalize_header
from schemabridge.domain.schema import TargetFieldSpec, TargetSchema, ValueKind
from schemabridge.domain.validate import run_validation_passes, validate_record
from schemabridge.server.target_client import build_payload

ORDERS = TargetSchema(
    schema_id="sch_orders",
    name="Order",
    description="A purchase order in the destination system.",
    fields=(
        TargetFieldSpec(
            name="orderRef",
            label="Order reference",
            kind=ValueKind.IDENTIFIER,
            required=True,
            is_identity=True,
        ),
        TargetFieldSpec(
            name="customerEmail",
            label="Customer email",
            kind=ValueKind.EMAIL,
            required=True,
            is_unique=True,
        ),
        TargetFieldSpec(name="placedDate", label="Placed date", kind=ValueKind.DATE, required=True),
        TargetFieldSpec(
            name="shippedDate", label="Shipped date", kind=ValueKind.DATE, not_before="placedDate"
        ),
        TargetFieldSpec(
            name="tier",
            label="Tier",
            kind=ValueKind.ENUM,
            enum_values=("standard", "express"),
            value_aliases={"normal": "standard", "fast": "express", "overnight": "express"},
        ),
    ),
)


def column(column_id: str, header: str, index: int = 0, file_id: str = "f1") -> SourceColumn:
    return SourceColumn(
        id=column_id,
        file_id=file_id,
        file_name=f"{file_id}.csv",
        header=header,
        normalized_header=normalize_header(header),
        index=index,
    )


def profile(column_id: str, header: str, samples: Sequence[str]) -> ColumnProfile:
    present = [value for value in samples if value]
    return ColumnProfile(
        column_id=column_id,
        header=header,
        file_name="f1.csv",
        total_count=len(samples),
        non_empty_count=len(present),
        distinct_count=len(set(present)),
        unique_ratio=1.0,
        detected_kinds=tuple(detect_value_kinds(present)),
        samples=tuple(present[:3]),
    )


def row(values: Mapping[str, str | None], file_id: str = "f1", number: int = 2) -> IncomingRow:
    return IncomingRow(
        values=dict(values),
        provenance=Provenance(file_id=file_id, file_name=f"{file_id}.csv", sheet=None, row=number),
    )


class TestMappingOnAnUnknownSchema:
    def test_derived_spellings_place_columns_nobody_listed(self) -> None:
        """No aliases were supplied, so these matches are entirely derived."""
        columns = [
            column("c1", "order_ref", 0),
            column("c2", "Customer Email", 1),
            column("c3", "placed_date", 2),
        ]
        profiles = [
            profile("c1", "order_ref", ["ORD-1", "ORD-2"]),
            profile("c2", "Customer Email", ["a@x.com", "b@x.com"]),
            profile("c3", "placed_date", ["2026-01-05", "2026-02-09"]),
        ]
        result = decide_mappings(columns, profiles, schema=ORDERS)
        applied = {d.column_id: d.target for d in result.decisions if d.target}
        assert applied == {"c1": "orderRef", "c2": "customerEmail", "c3": "placedDate"}

    def test_a_header_two_fields_share_is_ambiguous_without_being_listed(self) -> None:
        """The same escalation the built-in template gets for a bare "Date".

        Nothing enumerates "date" as ambiguous for this schema — it falls out of
        two date fields both claiming the spelling.
        """
        columns = [column("c1", "Date")]
        profiles = [profile("c1", "Date", ["2026-01-05", "2026-02-09"])]
        result = decide_mappings(columns, profiles, schema=ORDERS)

        assert result.decisions[0].outcome is MappingOutcome.ESCALATED
        assert result.decisions[0].target is None
        issue = next(i for i in result.issues if i.type is IssueType.AMBIGUOUS_MAPPING)
        assert "Placed date" in issue.reason and "Shipped date" in issue.reason

    def test_a_missing_required_field_blocks(self) -> None:
        columns = [column("c1", "order_ref"), column("c2", "placed_date", 1)]
        profiles = [
            profile("c1", "order_ref", ["ORD-1"]),
            profile("c2", "placed_date", ["2026-01-05"]),
        ]
        result = decide_mappings(columns, profiles, schema=ORDERS)
        missing = [i for i in result.issues if i.type is IssueType.REQUIRED_FIELD_UNMAPPED]
        assert [i.field_name for i in missing] == ["customerEmail"]
        assert missing[0].blocking

    def test_values_still_veto_a_matching_header(self) -> None:
        """Type compatibility is not an employee-specific rule."""
        columns = [column("c1", "Placed Date")]
        profiles = [profile("c1", "Placed Date", ["a@x.com", "b@x.com"])]
        result = decide_mappings(columns, profiles, schema=ORDERS)
        assert result.decisions[0].target is None


class TestIdentityOnAnUnknownSchema:
    def test_merging_keys_on_the_declared_identity_field(self) -> None:
        result = reconcile_identities(
            [
                row({"orderRef": "ORD-1", "customerEmail": "a@x.com"}),
                row({"orderRef": "ORD-1", "placedDate": "2026-01-05"}, file_id="f2"),
            ],
            schema=ORDERS,
        )
        assert result.merged_rows == 1
        assert len(result.records) == 1
        assert result.records[0].values["customerEmail"] == "a@x.com"
        assert result.records[0].values["placedDate"] == "2026-01-05"

    def test_a_disagreement_escalates_and_names_the_record(self) -> None:
        result = reconcile_identities(
            [
                row({"orderRef": "ORD-1", "tier": "standard"}),
                row({"orderRef": "ORD-1", "tier": "express"}, file_id="f2"),
            ],
            schema=ORDERS,
        )
        issue = next(i for i in result.issues if i.type is IssueType.IDENTITY_CONFLICT)
        # Named by its identity value, not by an internal record id.
        assert "ORD-1" in issue.reason
        assert issue.field_name == "tier"

    def test_an_equivalent_spelling_is_not_a_conflict(self) -> None:
        """The enum vocabulary is the schema's own, so "fast" means express."""
        result = reconcile_identities(
            [
                row({"orderRef": "ORD-1", "tier": "express"}),
                row({"orderRef": "ORD-1", "tier": "fast"}, file_id="f2"),
            ],
            schema=ORDERS,
        )
        assert result.issues == ()
        assert result.records[0].values["tier"] == "express"

    def test_uniqueness_is_flagged_on_the_declared_field(self) -> None:
        result = reconcile_identities(
            [
                row({"orderRef": "ORD-1", "customerEmail": "same@x.com"}),
                row({"orderRef": "ORD-2", "customerEmail": "SAME@x.com"}, number=3),
            ],
            schema=ORDERS,
        )
        duplicate = next(i for i in result.issues if i.type is IssueType.DUPLICATE_EMAIL)
        assert duplicate.field_name == "customerEmail"
        assert len(duplicate.record_ids) == 2
        # Worth a look, but not worth blocking the migration over.
        assert not duplicate.blocking

    def test_without_an_identity_field_every_row_stands_alone(self) -> None:
        """Not merging is the safe failure: no record is silently lost."""
        anonymous = TargetSchema(
            schema_id="sch_anon",
            name="Anonymous",
            fields=(TargetFieldSpec(name="note", label="Note"),),
        )
        result = reconcile_identities(
            [row({"note": "a"}), row({"note": "a"}, number=3)], schema=anonymous
        )
        assert len(result.records) == 2
        assert result.merged_rows == 0


class TestCleanupAndValidationOnAnUnknownSchema:
    def test_repairs_are_chosen_by_kind_not_by_name(self) -> None:
        result = apply_safe_repairs(
            {
                "customerEmail": " Buyer@EXAMPLE.COM ",
                "placedDate": "14 March 2026",
                "tier": "Overnight",
            },
            schema=ORDERS,
        )
        assert result.values["customerEmail"] == "Buyer@example.com"
        assert result.values["placedDate"] == "2026-03-14"
        assert result.values["tier"] == "express"

    def test_an_unlisted_enum_spelling_is_left_for_a_human(self) -> None:
        result = apply_safe_repairs({"tier": "whenever"}, schema=ORDERS)
        assert result.values["tier"] == "whenever"
        assert "tier" in result.unrepairable

    def test_an_exact_member_needs_no_alias_entry(self) -> None:
        assert normalize_enum_value("tier", "standard", schema=ORDERS) == "standard"
        assert normalize_enum_value("tier", "nonsense", schema=ORDERS) is None

    def test_email_syntax_applies_to_the_declared_email_field(self) -> None:
        outcome = validate_record(
            {
                "orderRef": "ORD-1",
                "customerEmail": "buyer@localhost",
                "placedDate": "2026-01-05",
            },
            schema=ORDERS,
        )
        assert not outcome.valid
        assert any(error.code == "email_syntax" for error in outcome.errors)

    def test_the_declared_date_pair_is_ordered(self) -> None:
        outcome = validate_record(
            {
                "orderRef": "ORD-1",
                "customerEmail": "buyer@example.com",
                "placedDate": "2026-05-01",
                "shippedDate": "2026-04-01",
            },
            schema=ORDERS,
        )
        assert not outcome.valid
        error = next(e for e in outcome.errors if e.code == "end_before_start")
        # Phrased in the schema's own words, not "end date"/"start date".
        assert "Shipped date" in error.message and "Placed date" in error.message

    def test_a_field_the_schema_does_not_define_is_refused(self) -> None:
        outcome = validate_record(
            {
                "orderRef": "ORD-1",
                "customerEmail": "buyer@example.com",
                "placedDate": "2026-01-05",
                "employeeId": "E-1",
            },
            schema=ORDERS,
        )
        assert not outcome.valid

    def test_two_passes_still_repair_then_accept(self) -> None:
        result = run_validation_passes(
            {
                "orderRef": "ORD-1",
                "customerEmail": " Buyer@EXAMPLE.COM ",
                "placedDate": "14 March 2026",
            },
            schema=ORDERS,
        )
        assert result.valid
        assert len(result.passes) == 2
        assert result.repairs


class TestDeliveryOnAnUnknownSchema:
    def test_the_payload_is_built_from_the_schema(self) -> None:
        from schemabridge.domain.models import CanonicalRecord

        record = CanonicalRecord(
            id="rec:ord-1",
            identity_key="ord-1",
            values={
                "orderRef": "ORD-1",
                "customerEmail": "buyer@example.com",
                "placedDate": "2026-01-05",
                "shippedDate": None,
                "tier": "",
                # Never part of this contract, so it must not be sent.
                "employeeId": "E-1",
            },
        )
        payload = build_payload(record, schema=ORDERS)
        assert payload == {
            "orderRef": "ORD-1",
            "customerEmail": "buyer@example.com",
            "placedDate": "2026-01-05",
        }


class TestNamingARecord:
    """A reviewer must always see a handle they can find in their own file."""

    def test_a_person_name_is_preferred(self) -> None:
        from schemabridge.domain.target import BUILTIN_SCHEMA

        assert BUILTIN_SCHEMA.naming_field == "fullName"

    def test_the_identity_field_is_next(self) -> None:
        assert ORDERS.naming_field == "orderRef"

    def test_an_identifier_serves_when_nothing_is_declared(self) -> None:
        """A detected schema declares no identity, and "rec:row-3" is useless.

        Display is a different question from merging: a guess is fine here and
        wrong only cosmetically, whereas guessing an identity field would merge
        or split records.
        """
        detected = TargetSchema(
            schema_id="detected",
            name="Detected",
            fields=(
                TargetFieldSpec(name="empId", label="Emp id", kind=ValueKind.IDENTIFIER),
                TargetFieldSpec(name="dept", label="Dept", kind=ValueKind.TEXT),
            ),
        )
        assert detected.identity_field is None
        assert detected.naming_field == "empId"

    def test_a_required_field_is_the_last_resort(self) -> None:
        schema = TargetSchema(
            schema_id="x",
            name="X",
            fields=(
                TargetFieldSpec(name="note", label="Note", kind=ValueKind.TEXT),
                TargetFieldSpec(name="code", label="Code", kind=ValueKind.TEXT, required=True),
            ),
        )
        assert schema.naming_field == "code"

    def test_a_conflict_names_the_record_by_its_naming_field(self) -> None:
        """The audit trail and the question both say "ORD-1", never "rec:ord-1"."""
        result = reconcile_identities(
            [
                row({"orderRef": "ORD-1", "tier": "standard"}),
                row({"orderRef": "ORD-1", "tier": "express"}, file_id="f2"),
            ],
            schema=ORDERS,
        )
        issue = next(i for i in result.issues if i.type is IssueType.IDENTITY_CONFLICT)
        assert issue.reason.startswith("ORD-1 ")


class TestIdentityAndDisplayAreDifferentQuestions:
    """Conflating them is a silent bug, so the distinction is pinned.

    Display prefers a person's name because that is what a reviewer recognises.
    Anything keyed on *which record this is* — merging, and the demo's per-record
    delivery behaviour — must use the identity field, which is only ever set
    deliberately. Looking a record up by its display name matches nothing.
    """

    def test_the_two_fields_differ_on_the_builtin_template(self) -> None:
        from schemabridge.domain.target import BUILTIN_SCHEMA

        assert BUILTIN_SCHEMA.identity_field == "employeeId"
        assert BUILTIN_SCHEMA.naming_field == "fullName"

    def test_merging_still_keys_on_identity_not_on_the_name(self) -> None:
        """Two people who share a name are not one record."""
        from schemabridge.domain.target import BUILTIN_SCHEMA

        result = reconcile_identities(
            [
                row({"employeeId": "E-1", "fullName": "Jo Smith"}),
                row({"employeeId": "E-2", "fullName": "Jo Smith"}, number=3),
            ],
            schema=BUILTIN_SCHEMA,
        )
        assert len(result.records) == 2
        assert result.merged_rows == 0


class TestValidatorIsolation:
    def test_two_schemas_do_not_share_a_validator(self) -> None:
        """The cache is keyed per schema, so one contract cannot judge another."""
        from schemabridge.domain.target import BUILTIN_SCHEMA

        employee = {
            "employeeId": "E-1",
            "fullName": "A B",
            "workEmail": "a@example.com",
            "startDate": "2026-01-05",
        }
        assert validate_record(employee, schema=BUILTIN_SCHEMA).valid
        assert not validate_record(employee, schema=ORDERS).valid

    def test_editing_a_schema_does_not_reuse_the_old_validator(self) -> None:
        """A bumped version must not be served the previous revision's rules."""
        loose = TargetSchema(
            schema_id="sch_edit",
            name="Thing",
            version=1,
            fields=(TargetFieldSpec(name="code", label="Code"),),
        )
        strict = loose.model_copy(
            update={
                "version": 2,
                "fields": (TargetFieldSpec(name="code", label="Code", required=True),),
            }
        )
        assert validate_record({}, schema=loose).valid
        assert not validate_record({}, schema=strict).valid
