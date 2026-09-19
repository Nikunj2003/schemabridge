"""What the browser is told about a run.

These cover two defects found by driving a real migration through the API rather
than by reading the code: a rejected record arrived with no reason attached, and
the column totals grew every time a reviewer corrected a mapping.
"""

from __future__ import annotations

from schemabridge.api.views import build_run_view
from schemabridge.domain.models import (
    Actor,
    CanonicalRecord,
    DeliveryAttempt,
    DeliveryIntent,
    DeliveryOutcome,
    DeliveryState,
    Disposition,
    MappingBasis,
    MappingDecision,
    MappingOutcome,
    Provenance,
    RunPhase,
    SourceColumn,
    SourceRow,
    ValidationError,
    ValidationPass,
    ValidationPassLabel,
)
from schemabridge.domain.target import TargetField


def _column(index: int, header: str) -> SourceColumn:
    return SourceColumn(
        id=f"f0:c{index}",
        file_id="f0",
        file_name="legacy.csv",
        header=header,
        normalized_header=header.lower(),
        index=index,
    )


def _state(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "run_id": "run_test",
        "phase": RunPhase.COMPLETE_WITH_FAILURES,
        "files": (),
        "columns": (),
        "rows": (),
        "mappings": (),
        "records": (),
        "issues": (),
        "deliveries": (),
        "events": (),
    }
    base.update(overrides)
    return base


def test_rejected_record_carries_the_destination_reason() -> None:
    """A failed delivery explains itself where the reader is looking.

    The record passed validation, so its validation errors are empty. Reading
    those for the failure reason leaves a red row with nothing beside it.
    """
    record = CanonicalRecord(
        id="rec:e-1008",
        values={"employeeId": "E-1008", "fullName": "Arjun Mehta"},
        provenance=(Provenance(file_id="f0", file_name="legacy.csv", row=9),),
        validation=(ValidationPass(label=ValidationPassLabel.AS_MAPPED, valid=True, errors=()),),
        disposition=Disposition.FAILED,
    )
    intent = DeliveryIntent(
        record_id="rec:e-1008",
        revision=1,
        idempotency_key="k",
        payload_hash="h",
        state=DeliveryState.FAILED,
        attempts=(
            DeliveryAttempt(
                attempt=1,
                status=422,
                outcome=DeliveryOutcome.FAILED,
                detail="Employee E-1008 is not permitted in this system",
            ),
        ),
    )

    view = build_run_view(
        "run_test",
        _state(records=(record,), deliveries=(intent,)),
        paused=False,
        runnable=False,
    )

    (failed,) = [r for r in view.records if r.disposition == "failed"]
    assert failed.errors == ["Employee E-1008 is not permitted in this system (HTTP 422)"]


def test_rejected_record_without_a_detail_still_says_something() -> None:
    """Never a blank explanation, even when the destination gave none."""
    record = CanonicalRecord(
        id="rec:x",
        values={"employeeId": "X"},
        validation=(ValidationPass(label=ValidationPassLabel.AS_MAPPED, valid=True, errors=()),),
        disposition=Disposition.FAILED,
    )
    view = build_run_view(
        "run_test", _state(records=(record,)), paused=False, runnable=False
    )
    assert view.records[0].errors == ["The destination refused this record."]


def test_validation_failures_keep_their_own_errors() -> None:
    """A record that never left is explained by its validation, not delivery."""
    record = CanonicalRecord(
        id="rec:y",
        values={"employeeId": "Y"},
        validation=(
            ValidationPass(
                label=ValidationPassLabel.AFTER_REPAIR,
                valid=False,
                errors=(
                    ValidationError(
                        field_name="workEmail",
                        code="format",
                        message="Not a usable email address.",
                    ),
                ),
            ),
        ),
        disposition=Disposition.NEEDS_REVIEW,
    )
    view = build_run_view(
        "run_test", _state(records=(record,)), paused=False, runnable=False
    )
    assert view.records[0].errors == ["Not a usable email address."]


def test_column_totals_report_current_state_not_attempts() -> None:
    """Correcting a mapping must not inflate the column count.

    Each correction appends a decision, so counting the whole history made
    "12 of 13 columns" climb toward "16 of 17" while the reviewer worked.
    """
    columns = (_column(0, "emp_id"), _column(1, "Date"))
    mappings = (
        MappingDecision(
            column_id="f0:c0",
            target=TargetField.EMPLOYEE_ID,
            outcome=MappingOutcome.AUTO_MAPPED,
            basis=MappingBasis.EXACT_NAME,
        ),
        # The agent could not decide about "Date"…
        MappingDecision(
            column_id="f0:c1",
            outcome=MappingOutcome.ESCALATED,
            basis=MappingBasis.UNMAPPED,
        ),
        # …and the reviewer then said what it meant.
        MappingDecision(
            column_id="f0:c1",
            target=TargetField.START_DATE,
            outcome=MappingOutcome.AUTO_MAPPED,
            basis=MappingBasis.HUMAN_CORRECTION,
            decided_by=Actor.REVIEWER,
        ),
    )

    view = build_run_view(
        "run_test",
        _state(columns=columns, mappings=mappings),
        paused=False,
        runnable=False,
    )

    assert view.counters.auto_mapped == 2
    assert view.counters.escalated == 0
    assert view.counters.auto_mapped + view.counters.escalated == len(columns)
    # The mapping list agrees: one entry per column, showing the current decision.
    assert len(view.mappings) == 2
    assert [m.decided_by for m in view.mappings if m.column == "Date"] == ["reviewer"]


def test_row_and_employee_counts_stay_separate_units() -> None:
    """Merged duplicates are reported, never folded into one total."""
    rows = tuple(
        SourceRow(id=f"r{i}", file_id="f0", row=i + 2, values={})
        for i in range(12)
    )
    records = tuple(
        CanonicalRecord(id=f"rec:{i}", values={"employeeId": f"E-{i}"}) for i in range(10)
    )
    view = build_run_view(
        "run_test", _state(rows=rows, records=records), paused=False, runnable=False
    )
    assert (view.counters.source_rows, view.counters.records, view.counters.merged) == (12, 10, 2)


def test_duplicates_are_not_reported_before_records_exist() -> None:
    """Rows with no records yet is not "every row was a duplicate".

    Bounded execution means the UI polls mid-run, when rows are parsed but
    reconciliation has not happened. Subtracting anyway told a person their clean
    3-row file had "3 duplicate rows combined".
    """
    rows = tuple(SourceRow(id=f"r{i}", file_id="f0", row=i + 2, values={}) for i in range(3))
    view = build_run_view(
        "run_test",
        _state(rows=rows, records=(), phase=RunPhase.ANALYZING),
        paused=False,
        runnable=True,
    )
    assert view.counters.source_rows == 3
    assert view.counters.records == 0
    assert view.counters.merged == 0
