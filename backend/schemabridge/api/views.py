"""How the workflow's state is presented to the browser.

Deliberately a projection, not a dump of the graph state. The UI needs the
decisions and their reasons; it does not need every source row, and sending them
would put the whole uploaded dataset back on the wire on every poll.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from schemabridge.domain.models import (
    AuditEvent,
    CanonicalRecord,
    DeliveryIntent,
    Disposition,
    IssueStatus,
    MappingOutcome,
    ReviewIssue,
    RunPhase,
)
from schemabridge.domain.target import TARGET_FIELDS, get_field


def _attr(value: Any, name: str, default: Any = None) -> Any:
    """Read a field whether it arrived as a model or as a plain dict.

    State read back through the checkpointer is deserialised, and nested values
    can surface as dicts rather than the models they were written as. The view
    layer is the boundary where that has to be tolerated; letting it leak further
    would mean every consumer needed the same defensive code.
    """
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _enum_value(value: Any, default: str = "") -> str:
    """The string form of an enum that may have been deserialised to a str."""
    if value is None:
        return default
    return str(getattr(value, "value", value))


#: Phases where the UI should keep polling.
_ACTIVE_PHASES = frozenset(
    {RunPhase.INGESTED, RunPhase.ANALYZING, RunPhase.READY, RunPhase.DELIVERING}
)


class MappingView(BaseModel):
    column: str
    file: str
    target: str | None
    target_label: str | None
    outcome: str
    basis: str
    evidence: list[str]
    decided_by: str


class RecordView(BaseModel):
    id: str
    employee_id: str | None
    values: dict[str, str | None]
    disposition: str
    sources: list[str]
    repairs: int
    valid: bool
    errors: list[str]
    exclusion_reason: str | None
    target_id: str | None


class IssueView(BaseModel):
    id: str
    type: str
    status: str
    reason: str
    blocking: bool
    field: str | None
    field_label: str | None
    current_value: str | None
    affected: int
    #: Which records this issue is about. The UI needs these to name the employee
    #: rather than matching on values, which is ambiguous when two people share
    #: a value and wrong when the issue is about a column rather than a record.
    record_ids: list[str]
    #: The source column's own header, for issues raised about a column.
    column: str | None
    column_file: str | None
    options: list[dict[str, Any]]
    errors: list[str]
    resolution: dict[str, Any] | None


class EventView(BaseModel):
    seq: int
    at: str
    actor: str
    action: str
    reason: str
    subject: str | None
    before: str | None
    after: str | None


class CountersView(BaseModel):
    source_rows: int
    records: int
    merged: int
    auto_mapped: int
    escalated: int
    repairs: int
    model_requests: int
    delivered: int
    failed: int
    excluded: int
    #: Delivered records still waiting on a scheduled retry. Surfaced so the
    #: totals reconcile and the UI can show that work remains.
    retrying: int
    awaiting_review: int


class RunView(BaseModel):
    run_id: str
    phase: str
    phase_label: str
    paused: bool
    runnable: bool
    active: bool
    files: list[str]
    counters: CountersView
    mappings: list[MappingView]
    issues: list[IssueView]
    records: list[RecordView]
    events: list[EventView]
    latest_seq: int
    blocked_reason: str | None


_PHASE_LABELS: dict[RunPhase, str] = {
    RunPhase.INGESTED: "Files received",
    RunPhase.ANALYZING: "Working out the mapping",
    RunPhase.REVIEW: "Waiting for your decision",
    RunPhase.READY: "Ready to deliver",
    RunPhase.DELIVERING: "Delivering to the destination",
    RunPhase.COMPLETE: "Complete",
    RunPhase.COMPLETE_WITH_FAILURES: "Complete, with failures",
    RunPhase.BLOCKED: "Blocked",
}


def _mapping_views(state: dict[str, Any]) -> list[MappingView]:
    columns = {_attr(column, "id"): column for column in state.get("columns", ())}
    views: list[MappingView] = []
    for decision in state.get("mappings", ()):
        column = columns.get(_attr(decision, "column_id"))
        target = _enum_value(_attr(decision, "target"), "") or None
        spec = get_field(target) if target else None
        views.append(
            MappingView(
                column=_attr(column, "header") or _attr(decision, "column_id", ""),
                file=_attr(column, "file_name", "") or "",
                target=target,
                target_label=spec.label if spec else None,
                outcome=_enum_value(_attr(decision, "outcome")),
                basis=_enum_value(_attr(decision, "basis")),
                evidence=list(_attr(decision, "evidence", ()) or ()),
                decided_by=_enum_value(_attr(decision, "decided_by"), "agent"),
            )
        )
    # A later correction supersedes the agent's original decision for a column.
    deduped: dict[str, MappingView] = {}
    for view in views:
        deduped[f"{view.file}:{view.column}"] = view
    return list(deduped.values())


def _last_delivery_detail(intent: Any) -> str | None:
    """Why the destination refused a record, in the destination's own words.

    Validation errors explain a record that never left; they say nothing about
    one the target rejected. Reading them for a failed delivery is how a failure
    ends up displayed with no reason at all.
    """
    attempts = _attr(intent, "attempts", ()) or ()
    for attempt in reversed(list(attempts)):
        detail = _attr(attempt, "detail", "")
        if detail:
            status = _attr(attempt, "status")
            return f"{detail} (HTTP {status})" if status else str(detail)
    return None


def _record_views(
    records: tuple[CanonicalRecord, ...], deliveries: tuple[DeliveryIntent, ...]
) -> list[RecordView]:
    targets = {_attr(intent, "record_id"): _attr(intent, "target_id") for intent in deliveries}
    refusals = {
        _attr(intent, "record_id"): _last_delivery_detail(intent) for intent in deliveries
    }
    views: list[RecordView] = []
    for record in records:
        validation = _attr(record, "validation", ()) or ()
        last = validation[-1] if validation else None
        values = dict(_attr(record, "values", {}) or {})
        errors = _attr(last, "errors", ()) if last is not None else ()
        disposition = _enum_value(_attr(record, "disposition"), "candidate")
        messages = [_attr(error, "message", "") for error in errors or ()]
        if disposition == Disposition.FAILED.value:
            # The destination's reason, not a stale validation message.
            refusal = refusals.get(_attr(record, "id"))
            messages = [refusal] if refusal else ["The destination refused this record."]
        views.append(
            RecordView(
                id=_attr(record, "id", ""),
                employee_id=values.get("employeeId"),
                values=values,
                disposition=disposition,
                sources=[
                    f"{_attr(p, 'file_name', '')} row {_attr(p, 'row', '?')}"
                    for p in _attr(record, "provenance", ()) or ()
                ],
                repairs=len(_attr(record, "repairs", ()) or ()),
                valid=bool(last is not None and _attr(last, "valid", False)),
                errors=messages,
                exclusion_reason=_attr(record, "exclusion_reason"),
                target_id=targets.get(_attr(record, "id")),
            )
        )
    return views


def _issue_views(
    issues: tuple[ReviewIssue, ...], columns: tuple[Any, ...] = ()
) -> list[IssueView]:
    by_id = {_attr(column, "id"): column for column in columns}
    views: list[IssueView] = []
    for issue in issues:
        field_name = _attr(issue, "field_name")
        column = by_id.get(_attr(issue, "column_id"))
        spec = get_field(field_name) if field_name else None
        resolution = _attr(issue, "resolution")
        resolved_at: Any = _attr(resolution, "resolved_at") if resolution else None
        views.append(
            IssueView(
                id=_attr(issue, "id", ""),
                type=_enum_value(_attr(issue, "type")),
                status=_enum_value(_attr(issue, "status"), "open"),
                reason=_attr(issue, "reason", ""),
                blocking=bool(_attr(issue, "blocking", True)),
                field=field_name,
                field_label=spec.label if spec else None,
                current_value=_attr(issue, "current_value"),
                affected=len(_attr(issue, "record_ids", ()) or ()),
                record_ids=list(_attr(issue, "record_ids", ()) or ()),
                column=_attr(column, "header") if column is not None else None,
                column_file=_attr(column, "file_name") if column is not None else None,
                options=[
                    {
                        "id": _attr(option, "id", ""),
                        "label": _attr(option, "label", ""),
                        "detail": _attr(option, "detail", ""),
                        "target": _enum_value(_attr(option, "target"), "") or None,
                        "value": _attr(option, "value"),
                    }
                    for option in _attr(issue, "options", ()) or ()
                ],
                errors=[
                    _attr(error, "message", "")
                    for error in _attr(issue, "detected_errors", ()) or ()
                ],
                resolution=(
                    {
                        "action": _enum_value(_attr(resolution, "action")),
                        "option_id": _attr(resolution, "option_id"),
                        "value": _attr(resolution, "value"),
                        "note": _attr(resolution, "note"),
                        "at": (
                            resolved_at.isoformat()
                            if hasattr(resolved_at, "isoformat")
                            else str(resolved_at or "")
                        ),
                    }
                    if resolution
                    else None
                ),
            )
        )
    return views


def _counters(state: dict[str, Any]) -> CountersView:
    records = state.get("records", ())
    mappings = state.get("mappings", ())
    issues = state.get("issues", ())

    def disposition_is(record: Any, wanted: Disposition) -> bool:
        return _enum_value(_attr(record, "disposition")) == wanted.value

    # One column can accumulate several decisions as it is corrected. Only the
    # latest one is the current state; counting them all reports a column total
    # that grows while the reviewer works.
    effective: dict[str, Any] = {}
    for decision in mappings:
        column_id = _attr(decision, "column_id")
        if column_id is not None:
            effective[column_id] = decision
    current = tuple(effective.values())

    # Rows minus records is only the duplicate count once the records exist.
    # Before reconciliation runs there are none, and the difference is the whole
    # dataset — which surfaced as "combined 3 duplicate rows" on a clean file
    # that had no duplicates at all.
    rows = len(state.get("rows", ()))
    merged = max(0, rows - len(records)) if records else 0

    return CountersView(
        source_rows=rows,
        records=len(records),
        merged=merged,
        auto_mapped=sum(
            1
            for m in current
            if _enum_value(_attr(m, "outcome")) == MappingOutcome.AUTO_MAPPED.value
        ),
        escalated=sum(
            1
            for m in current
            if _enum_value(_attr(m, "outcome")) == MappingOutcome.ESCALATED.value
        ),
        repairs=sum(len(_attr(record, "repairs", ()) or ()) for record in records),
        model_requests=int(state.get("model_requests", 0)),
        delivered=sum(1 for r in records if disposition_is(r, Disposition.DELIVERED)),
        failed=sum(1 for r in records if disposition_is(r, Disposition.FAILED)),
        excluded=sum(1 for r in records if disposition_is(r, Disposition.EXCLUDED)),
        retrying=sum(1 for r in records if disposition_is(r, Disposition.RETRY_WAIT)),
        awaiting_review=sum(
            1
            for issue in issues
            if _enum_value(_attr(issue, "status"), "open") == IssueStatus.OPEN.value
            and _attr(issue, "blocking", True)
        ),
    )


def _event_views(events: tuple[AuditEvent, ...], since: int) -> list[EventView]:
    views: list[EventView] = []
    for event in events:
        seq = int(_attr(event, "seq", 0))
        if seq <= since:
            continue
        at = _attr(event, "at")
        views.append(
            EventView(
                seq=seq,
                at=at.isoformat() if hasattr(at, "isoformat") else str(at or ""),
                actor=_enum_value(_attr(event, "actor"), "agent"),
                action=_attr(event, "action", ""),
                reason=_attr(event, "reason", ""),
                subject=_attr(event, "subject"),
                before=_attr(event, "before"),
                after=_attr(event, "after"),
            )
        )
    return views


def build_run_view(
    run_id: str,
    state: dict[str, Any],
    *,
    paused: bool,
    runnable: bool,
    since: int = 0,
) -> RunView:
    """Project the workflow state into what the browser needs."""
    phase = state.get("phase", RunPhase.INGESTED)
    if not isinstance(phase, RunPhase):
        phase = RunPhase(_enum_value(phase, RunPhase.INGESTED.value))
    events = state.get("events", ())

    return RunView(
        run_id=run_id,
        phase=phase.value,
        phase_label=_PHASE_LABELS.get(phase, phase.value),
        paused=paused,
        runnable=runnable,
        active=phase in _ACTIVE_PHASES and not paused,
        files=[_attr(source, "name", "") for source in state.get("files", ())],
        counters=_counters(state),
        mappings=_mapping_views(state),
        issues=_issue_views(state.get("issues", ()), tuple(state.get("columns", ()))),
        records=_record_views(state.get("records", ()), state.get("deliveries", ())),
        events=_event_views(events, since),
        latest_seq=max((int(_attr(event, "seq", 0)) for event in events), default=0),
        blocked_reason=state.get("blocked_reason"),
    )


def target_schema_view() -> list[dict[str, Any]]:
    """The target contract, so the UI can show what is being mapped onto."""
    return [
        {
            "name": spec.name.value,
            "label": spec.label,
            "description": spec.description,
            "required": spec.required,
            "kind": spec.kind.value,
            "allowed_values": list(spec.enum_values),
        }
        for spec in TARGET_FIELDS
    ]
