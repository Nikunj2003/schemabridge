"""The autonomy boundary: what the engine may decide without asking."""

from __future__ import annotations

from collections.abc import Sequence

from schemabridge.domain import mapping as mapping_module
from schemabridge.domain.mapping import MappingResult
from schemabridge.domain.models import ColumnProfile, IssueType, MappingOutcome, SourceColumn
from schemabridge.domain.normalize import detect_value_kinds, normalize_header
from schemabridge.domain.target import BUILTIN_SCHEMA, TargetField


def decide_mappings(
    columns: Sequence[SourceColumn], profiles: Sequence[ColumnProfile]
) -> MappingResult:
    """Map against the built-in template, which these gate tests are about."""
    return mapping_module.decide_mappings(columns, profiles, schema=BUILTIN_SCHEMA)


def column(column_id: str, header: str, index: int = 0, file_id: str = "f1") -> SourceColumn:
    return SourceColumn(
        id=column_id,
        file_id=file_id,
        file_name=f"{file_id}.csv",
        header=header,
        normalized_header=normalize_header(header),
        index=index,
    )


def profile(column_id: str, header: str, samples: list[str]) -> ColumnProfile:
    present = [s for s in samples if s.strip()]
    return ColumnProfile(
        column_id=column_id,
        header=header,
        file_name="f1.csv",
        total_count=len(samples),
        non_empty_count=len(present),
        distinct_count=len(set(present)),
        unique_ratio=(len(set(present)) / len(present)) if present else 0.0,
        detected_kinds=tuple(detect_value_kinds(present)),
        samples=tuple(present[:5]),
    )


class TestDeterministicGate:
    def test_auto_maps_an_exact_target_name(self) -> None:
        result = decide_mappings(
            [column("c1", "employeeId")], [profile("c1", "employeeId", ["E-1", "E-2"])]
        )
        decision = next(d for d in result.decisions if d.column_id == "c1")
        assert decision.outcome is MappingOutcome.AUTO_MAPPED
        assert decision.target == TargetField.EMPLOYEE_ID
        assert decision.basis == "exact_name"

    def test_auto_maps_a_known_alias_with_compatible_values(self) -> None:
        result = decide_mappings(
            [column("c1", "emp_nm")],
            [profile("c1", "emp_nm", ["Priya Sharma", "John Smith"])],
        )
        decision = next(d for d in result.decisions if d.column_id == "c1")
        assert decision.outcome is MappingOutcome.AUTO_MAPPED
        assert decision.target == TargetField.FULL_NAME
        assert decision.basis == "alias"

    def test_explains_itself_rather_than_emitting_a_score(self) -> None:
        result = decide_mappings(
            [column("c1", "doj")], [profile("c1", "doj", ["2026-01-01", "2026-02-02"])]
        )
        decision = next(d for d in result.decisions if d.column_id == "c1")
        assert decision.evidence
        joined = " ".join(decision.evidence).lower()
        assert "alias" in joined or "values" in joined or "spelling" in joined

    def test_does_not_auto_map_when_values_contradict_the_header(self) -> None:
        # Header says start date, values are clearly emails.
        result = decide_mappings(
            [column("c1", "start_date")],
            [profile("c1", "start_date", ["a@b.com", "c@d.com", "e@f.com"])],
        )
        decision = next(d for d in result.decisions if d.column_id == "c1")
        assert decision.outcome is not MappingOutcome.AUTO_MAPPED


class TestEscalationGate:
    def test_escalates_when_two_columns_compete_for_one_target(self) -> None:
        result = decide_mappings(
            [column("c1", "employee_id", 0), column("c2", "emp_code", 1)],
            [
                profile("c1", "employee_id", ["E-1", "E-2"]),
                profile("c2", "emp_code", ["X-1", "X-2"]),
            ],
        )
        assert any(i.type is IssueType.COMPETING_COLUMNS for i in result.issues)
        mapped = [
            d
            for d in result.decisions
            if d.target == TargetField.EMPLOYEE_ID and d.outcome is MappingOutcome.AUTO_MAPPED
        ]
        assert len(mapped) <= 1

    def test_escalates_an_ambiguous_header(self) -> None:
        # A bare "date" column could be a start date or an end date.
        result = decide_mappings(
            [column("c1", "date")], [profile("c1", "date", ["2026-01-01", "2026-02-02"])]
        )
        decision = next(d for d in result.decisions if d.column_id == "c1")
        assert decision.outcome is MappingOutcome.ESCALATED

        issue = next(i for i in result.issues if i.type is IssueType.AMBIGUOUS_MAPPING)
        assert len(issue.options) >= 2
        assert issue.blocking
        # The reason has to be readable by a non-technical reviewer.
        assert "could be" in issue.reason.lower()

    def test_reports_a_required_target_with_no_candidate(self) -> None:
        result = decide_mappings(
            [column("c1", "employee_id")], [profile("c1", "employee_id", ["E-1", "E-2"])]
        )
        missing = {
            i.field_name for i in result.issues if i.type is IssueType.REQUIRED_FIELD_UNMAPPED
        }
        assert {"fullName", "workEmail", "startDate"} <= missing

    def test_leaves_an_unrecognised_column_for_the_model(self) -> None:
        result = decide_mappings(
            [column("c1", "cost_centre_ref")],
            [profile("c1", "cost_centre_ref", ["CC-1", "CC-2"])],
        )
        decision = next(d for d in result.decisions if d.column_id == "c1")
        assert decision.outcome is not MappingOutcome.AUTO_MAPPED
        assert "c1" in result.unresolved

    def test_does_not_escalate_an_absent_optional_field(self) -> None:
        columns = [
            column("c1", "employee_id", 0),
            column("c2", "full_name", 1),
            column("c3", "work_email", 2),
            column("c4", "start_date", 3),
        ]
        profiles = [
            profile("c1", "employee_id", ["E-1"]),
            profile("c2", "full_name", ["Priya Sharma"]),
            profile("c3", "work_email", ["a@b.com"]),
            profile("c4", "start_date", ["2026-01-01"]),
        ]
        result = decide_mappings(columns, profiles)
        assert result.issues == ()


class TestCrossFileReconciliation:
    def test_same_target_from_different_files_is_reconciliation(self) -> None:
        """This distinction is the whole point of multi-file ingestion.

        Two files each supplying an employee ID is what we are asked to
        reconcile. Two columns in *one* file claiming it is a real ambiguity.
        """
        result = decide_mappings(
            [column("a1", "emp_id", 0, "fileA"), column("b1", "Employee Number", 0, "fileB")],
            [
                profile("a1", "emp_id", ["E-1", "E-2"]),
                profile("b1", "Employee Number", ["E-3", "E-4"]),
            ],
        )
        assert not any(i.type is IssueType.COMPETING_COLUMNS for i in result.issues)
        mapped = [
            d
            for d in result.decisions
            if d.target == TargetField.EMPLOYEE_ID and d.outcome is MappingOutcome.AUTO_MAPPED
        ]
        assert len(mapped) == 2
