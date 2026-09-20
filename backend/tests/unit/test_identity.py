"""Merging is conservative: same ID, and nothing in disagreement."""

from __future__ import annotations

from collections.abc import Sequence

from schemabridge.domain import identity as identity_module
from schemabridge.domain.identity import IncomingRow, ReconcileResult
from schemabridge.domain.models import Disposition, IssueType, Provenance
from schemabridge.domain.target import BUILTIN_SCHEMA


def reconcile_identities(rows: Sequence[IncomingRow]) -> ReconcileResult:
    """Reconcile against the built-in template.

    These cases are about the merge policy itself; `test_schema.py` covers
    reconciliation keyed on a different schema's identity field.
    """
    return identity_module.reconcile_identities(rows, schema=BUILTIN_SCHEMA)


def prov(file_id: str, row: int) -> Provenance:
    return Provenance(file_id=file_id, file_name=f"{file_id}.csv", sheet=None, row=row)


def row(values: dict[str, str | None], file_id: str, line: int) -> IncomingRow:
    return IncomingRow(values=values, provenance=prov(file_id, line))


class TestReconcileIdentities:
    def test_merges_identical_rows_across_files(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-1002", "fullName": "Rahul Verma"}, "legacy", 3),
                row({"employeeId": "E-1002", "fullName": "Rahul Verma"}, "hr", 7),
            ]
        )
        assert len(result.records) == 1
        assert len(result.records[0].provenance) == 2
        assert result.issues == ()

    def test_fills_a_gap_from_the_other_file(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-1", "fullName": "Asha Rao", "department": ""}, "legacy", 2),
                row(
                    {"employeeId": "E-1", "fullName": "Asha Rao", "department": "Finance"},
                    "hr",
                    5,
                ),
            ]
        )
        assert len(result.records) == 1
        assert result.records[0].values["department"] == "Finance"
        assert result.issues == ()

    def test_escalates_conflicting_values_for_one_id(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-9", "startDate": "2026-01-01"}, "legacy", 4),
                row({"employeeId": "E-9", "startDate": "2024-06-15"}, "hr", 9),
            ]
        )
        conflict = next(i for i in result.issues if i.type is IssueType.IDENTITY_CONFLICT)
        assert conflict.blocking
        offered = {o.value for o in conflict.options}
        assert {"2026-01-01", "2024-06-15"} <= offered
        assert len(result.records) == 1
        assert result.records[0].disposition is Disposition.NEEDS_REVIEW

    def test_flags_one_email_under_two_ids(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-1", "workEmail": "shared@example.com"}, "legacy", 2),
                row({"employeeId": "E-2", "workEmail": "shared@example.com"}, "legacy", 3),
            ]
        )
        duplicate = next(i for i in result.issues if i.type is IssueType.DUPLICATE_EMAIL)
        assert len(duplicate.record_ids) == 2

    def test_never_merges_on_name_similarity(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-1", "fullName": "Jon Smith"}, "legacy", 2),
                row({"employeeId": "E-2", "fullName": "John Smith"}, "legacy", 3),
            ]
        )
        assert len(result.records) == 2
        assert result.issues == ()

    def test_rows_without_an_identity_stay_separate(self) -> None:
        result = reconcile_identities(
            [
                row({"fullName": "No Id Here"}, "legacy", 2),
                row({"fullName": "Also None"}, "legacy", 3),
            ]
        )
        assert len(result.records) == 2
        assert result.records[0].identity_key is None

    def test_id_matching_ignores_case_and_spacing(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "e-1001", "fullName": "Same Person"}, "a", 2),
                row({"employeeId": " E-1001 ", "fullName": "Same Person"}, "b", 2),
            ]
        )
        assert len(result.records) == 1
        # The stored value keeps the original spelling, not the match key.
        assert result.records[0].values["employeeId"] == "e-1001"

    def test_every_input_row_is_accounted_for(self) -> None:
        rows = [
            row({"employeeId": "E-1", "fullName": "A"}, "a", 2),
            row({"employeeId": "E-1", "fullName": "A"}, "b", 3),
            row({"employeeId": "E-2", "fullName": "B"}, "a", 4),
        ]
        result = reconcile_identities(rows)
        assert sum(len(r.provenance) for r in result.records) == len(rows)


class TestSpellingIsNotDisagreement:
    """A false conflict is not a harmless extra prompt.

    It teaches the reviewer to click through the queue, which is how the real
    conflict two rows later gets approved without being read.
    """

    def test_merges_enum_values_differing_only_in_spelling(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-1", "employmentType": "full-time"}, "legacy", 3),
                row({"employeeId": "E-1", "employmentType": "Permanent"}, "hr", 2),
            ]
        )
        assert result.issues == ()
        assert len(result.records) == 1
        assert result.records[0].values["employmentType"] == "full_time"

    def test_merges_dates_written_differently(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-2", "startDate": "14 March 2026"}, "a", 2),
                row({"employeeId": "E-2", "startDate": "2026-03-14"}, "b", 2),
            ]
        )
        assert result.issues == ()
        assert result.records[0].values["startDate"] == "2026-03-14"

    def test_merges_emails_differing_by_domain_case(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-3", "workEmail": "a.b@EXAMPLE.COM"}, "a", 2),
                row({"employeeId": "E-3", "workEmail": "a.b@example.com"}, "b", 2),
            ]
        )
        assert result.issues == ()

    def test_still_escalates_a_genuine_enum_disagreement(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-4", "employmentType": "Full Time"}, "a", 2),
                row({"employeeId": "E-4", "employmentType": "Intern"}, "b", 2),
            ]
        )
        assert any(i.type is IssueType.IDENTITY_CONFLICT for i in result.issues)

    def test_still_escalates_genuinely_different_dates(self) -> None:
        result = reconcile_identities(
            [
                row({"employeeId": "E-5", "startDate": "2026-01-06"}, "a", 2),
                row({"employeeId": "E-5", "startDate": "2024-11-30"}, "b", 2),
            ]
        )
        assert any(i.type is IssueType.IDENTITY_CONFLICT for i in result.issues)

    def test_an_ambiguous_date_cannot_masquerade_as_agreement(self) -> None:
        # 03/04/2026 has no safe reading, so it cannot be declared equal to
        # either candidate interpretation.
        result = reconcile_identities(
            [
                row({"employeeId": "E-6", "startDate": "03/04/2026"}, "a", 2),
                row({"employeeId": "E-6", "startDate": "2026-04-03"}, "b", 2),
            ]
        )
        assert any(i.type is IssueType.IDENTITY_CONFLICT for i in result.issues)
