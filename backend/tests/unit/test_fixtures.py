"""Asserts the shipped sample files produce exactly the decisions claimed.

If a policy change alters what the engine does automatically versus what it
escalates, this is where it surfaces.

Everything here runs against the built-in template, which is the contract the
sample files were written for. That is the point: these assertions are the
guarantee that making schemas user-definable did not change what the shipped demo
does. `test_schema.py` covers other schemas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from schemabridge.agent.induce import propose_rule_from_model_mapping
from schemabridge.domain import identity as identity_module
from schemabridge.domain import mapping as mapping_module
from schemabridge.domain import validate as validate_module
from schemabridge.domain.cleanup import SourceValues
from schemabridge.domain.identity import IncomingRow, ReconcileResult
from schemabridge.domain.mapping import MappingResult
from schemabridge.domain.models import (
    ColumnProfile,
    Disposition,
    IssueType,
    MappingDecision,
    MappingOutcome,
    Provenance,
    SourceColumn,
    SourceRow,
)
from schemabridge.domain.target import BUILTIN_SCHEMA
from schemabridge.domain.validate import TwoPassResult
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.profile import profile_columns
from schemabridge.ingest.xlsx_source import parse_xlsx

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"


def decide_mappings(
    columns: Sequence[SourceColumn], profiles: Sequence[ColumnProfile]
) -> MappingResult:
    return mapping_module.decide_mappings(columns, profiles, schema=BUILTIN_SCHEMA)


def reconcile_identities(rows: Sequence[IncomingRow]) -> ReconcileResult:
    return identity_module.reconcile_identities(rows, schema=BUILTIN_SCHEMA)


def run_validation_passes(values: SourceValues) -> TwoPassResult:
    return validate_module.run_validation_passes(values, schema=BUILTIN_SCHEMA)


@dataclass(frozen=True, slots=True)
class Loaded:
    columns: tuple[SourceColumn, ...]
    profiles: tuple[ColumnProfile, ...]
    rows: tuple[SourceRow, ...]
    file_name: str


def load_csv(name: str, file_id: str) -> Loaded:
    parsed = parse_csv(file_id, name, (SAMPLES / name).read_text(encoding="utf-8"))
    assert parsed.ok, parsed.error
    return Loaded(
        columns=parsed.file.columns,
        profiles=profile_columns(parsed.file, parsed.rows),
        rows=parsed.rows,
        file_name=name,
    )


def load_xlsx(name: str, file_id: str) -> Loaded:
    parsed = parse_xlsx(file_id, name, (SAMPLES / name).read_bytes())
    assert parsed.ok, parsed.error
    return Loaded(
        columns=parsed.file.columns,
        profiles=profile_columns(parsed.file, parsed.rows),
        rows=parsed.rows,
        file_name=name,
    )


def project(sources: list[Loaded], decisions: tuple[MappingDecision, ...]) -> list[IncomingRow]:
    """Apply the accepted mappings to produce target-shaped rows."""
    target_by_column = {
        d.column_id: d.target
        for d in decisions
        if d.outcome is MappingOutcome.AUTO_MAPPED and d.target is not None
    }
    projected: list[IncomingRow] = []
    for source in sources:
        for row in source.rows:
            values: dict[str, str | None] = {}
            for column_id, raw in row.values.items():
                if target := target_by_column.get(column_id):
                    values[target] = raw
            projected.append(
                IncomingRow(
                    values=values,
                    provenance=Provenance(
                        file_id=row.file_id,
                        file_name=source.file_name,
                        sheet=None,
                        row=row.row,
                    ),
                )
            )
    return projected


@pytest.fixture(scope="module")
def messy() -> tuple[Loaded, Loaded, object]:
    legacy = load_csv("employees-legacy.csv", "legacy")
    hr = load_csv("employees-hr-export.csv", "hr")
    result = decide_mappings([*legacy.columns, *hr.columns], [*legacy.profiles, *hr.profiles])
    return legacy, hr, result


class TestMessyMultiFileMigration:
    def test_maps_terse_legacy_headers_without_being_told_how(
        self, messy: tuple[Loaded, Loaded, object]
    ) -> None:
        legacy, _hr, result = messy
        applied = {d.column_id: d.target for d in result.decisions if d.target}  # type: ignore[attr-defined]

        def target_for(source: Loaded, header: str) -> object:
            column = next(c for c in source.columns if c.header == header)
            return applied.get(column.id)

        assert target_for(legacy, "emp_id") == "employeeId"
        assert target_for(legacy, "emp_nm") == "fullName"
        assert target_for(legacy, "email") == "workEmail"
        assert target_for(legacy, "doj") == "startDate"
        assert target_for(legacy, "dept") == "department"
        assert target_for(legacy, "emp_type") == "employmentType"

    def test_reconciles_different_spellings_in_the_second_file(
        self, messy: tuple[Loaded, Loaded, object]
    ) -> None:
        _legacy, hr, result = messy
        applied = {d.column_id: d.target for d in result.decisions if d.target}  # type: ignore[attr-defined]

        def target_for(header: str) -> object:
            return applied.get(next(c for c in hr.columns if c.header == header).id)

        assert target_for("Employee Number") == "employeeId"
        assert target_for("Full Name") == "fullName"
        assert target_for("Work Email") == "workEmail"
        assert target_for("Joining Date") == "startDate"
        assert target_for("Division") == "department"

    def test_escalates_the_bare_date_column(self, messy: tuple[Loaded, Loaded, object]) -> None:
        _legacy, hr, result = messy
        date_column = next(c for c in hr.columns if c.header == "Date")
        decision = next(d for d in result.decisions if d.column_id == date_column.id)  # type: ignore[attr-defined]
        assert decision.outcome is MappingOutcome.ESCALATED

        issue = next(i for i in result.issues if i.column_id == date_column.id)  # type: ignore[attr-defined]
        assert issue.type is IssueType.AMBIGUOUS_MAPPING
        assert issue.blocking
        offered = {o.target for o in issue.options if o.target}
        assert {"startDate", "endDate"} <= offered
        assert "could be" in issue.reason.lower()

    def test_escalates_only_what_is_genuinely_ambiguous(
        self, messy: tuple[Loaded, Loaded, object]
    ) -> None:
        _legacy, _hr, result = messy
        escalated = [d for d in result.decisions if d.outcome is MappingOutcome.ESCALATED]  # type: ignore[attr-defined]
        automatic = [d for d in result.decisions if d.outcome is MappingOutcome.AUTO_MAPPED]  # type: ignore[attr-defined]
        # Not everything, and not nothing.
        assert len(escalated) == 1
        assert len(automatic) > len(escalated)

    def test_merges_the_duplicate_and_flags_the_conflict(
        self, messy: tuple[Loaded, Loaded, object]
    ) -> None:
        legacy, hr, result = messy
        rows = project([legacy, hr], result.decisions)  # type: ignore[attr-defined]
        reconciled = reconcile_identities(rows)

        assert reconciled.merged_rows > 0

        # E-1002 agrees in both files once spellings are canonicalised.
        merged = next(r for r in reconciled.records if r.identity_key == "e-1002")
        assert len(merged.provenance) == 2
        assert not any(merged.id in i.record_ids for i in reconciled.issues)

        # E-1003 has two different joining dates: one record, escalated.
        conflicted = next(r for r in reconciled.records if r.identity_key == "e-1003")
        assert conflicted.disposition is Disposition.NEEDS_REVIEW
        conflict = next(
            i
            for i in reconciled.issues
            if i.type is IssueType.IDENTITY_CONFLICT and conflicted.id in i.record_ids
        )
        assert conflict.field_name == "startDate"
        assert len(conflict.options) == 2

    def test_fixes_what_it_can_and_escalates_what_it_cannot(
        self, messy: tuple[Loaded, Loaded, object]
    ) -> None:
        legacy, hr, result = messy
        rows = project([legacy, hr], result.decisions)  # type: ignore[attr-defined]
        records = reconcile_identities(rows).records
        outcomes = {r.identity_key: run_validation_passes(r.values) for r in records}

        # Whitespace, casing and a month-name date are all repaired silently.
        priya = outcomes["e-1001"]
        assert priya.valid
        assert priya.values["fullName"] == "Priya Sharma"
        assert priya.values["workEmail"] == "Priya.Sharma@example.com"
        assert priya.values["startDate"] == "2026-03-14"

        # Leading zeros survive.
        assert outcomes["000123"].valid
        assert outcomes["000123"].values["employeeId"] == "000123"

        # An unrepairable email fails both passes.
        meera = outcomes["e-1005"]
        assert meera.failed_twice
        assert len(meera.passes) == 2

        # An ambiguous date is never silently resolved.
        vikram = outcomes["e-1004"]
        assert not vikram.valid
        assert vikram.values["startDate"] == "03/04/2026"

    def test_accounts_for_every_source_row(self, messy: tuple[Loaded, Loaded, object]) -> None:
        legacy, hr, result = messy
        rows = project([legacy, hr], result.decisions)  # type: ignore[attr-defined]
        records = reconcile_identities(rows).records
        assert sum(len(r.provenance) for r in records) == len(rows)
        assert result.unresolved == ()  # type: ignore[attr-defined]


class TestCleanFileNeedsNoHumanInput:
    def test_maps_validates_and_is_ready_with_zero_escalations(self) -> None:
        clean = load_csv("employees-clean.csv", "clean")
        result = decide_mappings(clean.columns, clean.profiles)

        assert result.issues == ()
        assert all(d.outcome is MappingOutcome.AUTO_MAPPED for d in result.decisions)

        rows = project([clean], result.decisions)
        reconciled = reconcile_identities(rows)
        assert reconciled.issues == ()

        for record in reconciled.records:
            outcome = run_validation_passes(record.values)
            assert outcome.valid
            # Already clean, so one evaluation is enough.
            assert len(outcome.passes) == 1


class TestExcelWorkbook:
    def test_resolves_typed_dates_and_leaves_an_unknown_header(self) -> None:
        book = load_xlsx("employees-directory.xlsx", "dir")
        result = decide_mappings(book.columns, book.profiles)

        applied = {d.column_id: d.target for d in result.decisions if d.target}

        def column_id(header: str) -> str:
            return next(c for c in book.columns if c.header == header).id

        assert applied.get(column_id("Staff ID")) == "employeeId"
        assert applied.get(column_id("Company Email")) == "workEmail"
        assert applied.get(column_id("Joining Date")) == "startDate"

        # Excel stored these as real dates; they arrive as calendar dates.
        assert book.rows[0].values[column_id("Joining Date")].count("-") == 2

        # No alias table knows this header. That is the model's job.
        assert column_id("Cost Centre Ref") in result.unresolved


class TestLearningSample:
    def test_offers_a_reusable_rule_after_a_verified_model_mapping(self) -> None:
        learning = load_csv("employees-rule-learning.csv", "learning")
        result = decide_mappings(learning.columns, learning.profiles)
        identifier = next(
            column for column in learning.columns if column.header == "Workforce Identifier"
        )

        # It needs model assistance the first time; every other header is known.
        assert result.unresolved == (identifier.id,)

        # Once that proposal is independently verified as Employee ID, the rule
        # proposal is deterministic and free: the next run can avoid the model.
        proposal = propose_rule_from_model_mapping(
            identifier.header,
            "employeeId",
            ("Verified model suggestion.",),
            schema=BUILTIN_SCHEMA,
            run_id="learning-run",
        )
        assert proposal is not None
        # Rules store their header key normalised, so spelling/case differences
        # in the next export still match the approved convention.
        assert proposal.rule.header == "workforceidentifier"
        assert proposal.rule.field_name == "employeeId"
        assert proposal.scope.value == "column"
