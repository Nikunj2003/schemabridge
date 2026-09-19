"""Workflow nodes.

Each node is a thin adapter: it pulls what it needs from the state, calls the
pure domain functions, and returns the delta. Keeping the decisions in
`schemabridge.domain` means they stay testable without a graph, a database, or a
model — and it keeps the escalation policy in one place rather than scattered
across orchestration code.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from schemabridge.domain.identity import IncomingRow, reconcile_identities
from schemabridge.domain.mapping import POLICY_VERSION, decide_mappings
from schemabridge.domain.models import (
    Actor,
    AuditEvent,
    CanonicalRecord,
    Disposition,
    IssueOption,
    IssueResolution,
    IssueStatus,
    IssueType,
    MappingBasis,
    MappingDecision,
    MappingOutcome,
    Provenance,
    ResolutionAction,
    ReviewIssue,
    RunPhase,
    ValidationError,
)
from schemabridge.domain.target import TargetField, get_field
from schemabridge.domain.validate import run_validation_passes
from schemabridge.graph.state import MigrationState, next_sequence


def _event(
    seq: int,
    action: str,
    reason: str,
    *,
    actor: Actor = Actor.AGENT,
    subject: str | None = None,
    before: str | None = None,
    after: str | None = None,
    **detail: str | int | float | bool | None,
) -> AuditEvent:
    return AuditEvent(
        seq=seq,
        actor=actor,
        action=action,
        reason=reason,
        subject=subject,
        before=before,
        after=after,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def propose_mappings(state: MigrationState) -> dict[str, Any]:
    """Decide which source column becomes which target field."""
    columns = state.get("columns", ())
    profiles = state.get("profiles", ())
    seq = next_sequence(state)

    result = decide_mappings(columns, profiles)

    events: list[AuditEvent] = []
    for decision in result.decisions:
        column = next((c for c in columns if c.id == decision.column_id), None)
        header = column.header if column else decision.column_id

        if decision.outcome is MappingOutcome.AUTO_MAPPED and decision.target:
            spec = get_field(decision.target.value)
            events.append(
                _event(
                    seq,
                    "mapping_applied",
                    decision.evidence[0] if decision.evidence else "Deterministic match.",
                    subject=header,
                    after=spec.label if spec else decision.target.value,
                    basis=decision.basis.value,
                )
            )
        else:
            events.append(
                _event(
                    seq,
                    "mapping_escalated",
                    decision.evidence[0] if decision.evidence else "No confident match.",
                    subject=header,
                )
            )
        seq += 1

    automatic = sum(1 for d in result.decisions if d.outcome is MappingOutcome.AUTO_MAPPED)
    events.append(
        _event(
            seq,
            "mapping_summary",
            f"{automatic} of {len(result.decisions)} columns mapped without asking.",
            automatic=automatic,
            escalated=len(result.decisions) - automatic,
        )
    )

    return {
        "mappings": result.decisions,
        "issues": result.issues,
        "unresolved_columns": result.unresolved,
        "events": tuple(events),
        "phase": RunPhase.ANALYZING,
        "policy_version": POLICY_VERSION,
    }


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


def _issue_payload(issue: ReviewIssue) -> dict[str, Any]:
    """What the reviewer sees. Enough context to decide in one glance."""
    return {
        "id": issue.id,
        "type": issue.type.value,
        "reason": issue.reason,
        "field": issue.field_name,
        "column_id": issue.column_id,
        "current_value": issue.current_value,
        "affected_records": len(issue.record_ids),
        "options": [
            {
                "id": option.id,
                "label": option.label,
                "detail": option.detail,
                "target": option.target.value if option.target else None,
                "value": option.value,
            }
            for option in issue.options
        ],
        "errors": [{"field": e.field_name, "message": e.message} for e in issue.detected_errors],
    }


def await_review(state: MigrationState) -> dict[str, Any]:
    """Pause for the reviewer, but only on issues that genuinely block progress.

    `interrupt()` suspends the run with its state checkpointed, so the decision
    can arrive in a later request — or a different process. Non-blocking issues
    are surfaced in the UI without stopping the migration.
    """
    issues = state.get("issues", ())
    blocking = [issue for issue in issues if issue.blocking and issue.status is IssueStatus.OPEN]

    if not blocking:
        return {"phase": RunPhase.READY}

    # The payload is what the caller receives; the return value is whatever the
    # reviewer sends back via Command(resume=...).
    decisions: dict[str, Any] = interrupt(
        {
            "kind": "review_required",
            "count": len(blocking),
            "issues": [_issue_payload(issue) for issue in blocking],
        }
    )

    seq = next_sequence(state)
    resolved: list[ReviewIssue] = []
    events: list[AuditEvent] = []

    for issue in blocking:
        choice = decisions.get(issue.id) if isinstance(decisions, dict) else None
        if not isinstance(choice, dict):
            continue  # Left unresolved; it stays blocking.

        action = ResolutionAction(choice.get("action", "approve"))
        option_id = choice.get("option_id")
        value = choice.get("value")
        note = choice.get("note")

        resolved.append(
            issue.model_copy(
                update={
                    "status": IssueStatus.RESOLVED,
                    "resolution": IssueResolution(
                        action=action,
                        option_id=option_id,
                        value=value,
                        note=note,
                        resolved_by=Actor.REVIEWER,
                    ),
                }
            )
        )
        events.append(
            _event(
                seq,
                f"issue_{action.value}",
                note or f"Reviewer chose to {action.value} this case.",
                actor=Actor.REVIEWER,
                subject=issue.field_name or issue.column_id,
                after=option_id or value,
            )
        )
        seq += 1

    return {
        "issues": tuple(resolved),
        "resolutions": {**state.get("resolutions", {}), **(decisions or {})},
        "events": tuple(events),
    }


def apply_resolutions(state: MigrationState) -> dict[str, Any]:
    """Turn reviewer decisions into mappings the pipeline can use.

    A correction is a new decision attributed to the reviewer, not a silent
    overwrite of the agent's — the audit trail has to show who decided what.
    """
    resolutions = state.get("resolutions", {})
    if not resolutions:
        return {}

    issues = {issue.id: issue for issue in state.get("issues", ())}
    columns = {column.id: column for column in state.get("columns", ())}

    added: list[MappingDecision] = []
    events: list[AuditEvent] = []
    seq = next_sequence(state)

    for issue_id, choice in resolutions.items():
        issue = issues.get(issue_id)
        if issue is None or not isinstance(choice, dict):
            continue

        action = ResolutionAction(choice.get("action", "approve"))
        if action in {ResolutionAction.REJECT, ResolutionAction.EXCLUDE}:
            continue  # Nothing to map; handled as a disposition instead.

        option_id = choice.get("option_id") or ""
        option = next((o for o in issue.options if o.id == option_id), None)

        # A mapping decision: either "map this column to that field", or
        # "use this column for a field nothing supplied".
        if option and option.target:
            column_id = issue.column_id or option_id.removeprefix("use:")
            if column_id in columns:
                spec = get_field(option.target.value)
                label = spec.label if spec else option.target.value
                added.append(
                    MappingDecision(
                        column_id=column_id,
                        target=option.target,
                        outcome=MappingOutcome.AUTO_MAPPED,
                        basis=MappingBasis.HUMAN_CORRECTION,
                        evidence=(f"Reviewer chose {label}.",),
                        decided_by=Actor.REVIEWER,
                    )
                )
                events.append(
                    _event(
                        seq,
                        "mapping_corrected",
                        f"Reviewer mapped this column to {label}.",
                        actor=Actor.REVIEWER,
                        subject=columns[column_id].header,
                        after=option.target.value,
                    )
                )
                seq += 1

    return {"mappings": tuple(added), "events": tuple(events)}


# ---------------------------------------------------------------------------
# Reconciliation and validation
# ---------------------------------------------------------------------------


def _accepted_targets(state: MigrationState) -> dict[str, TargetField]:
    """Column to target, with reviewer corrections taking precedence."""
    accepted: dict[str, TargetField] = {}
    for decision in state.get("mappings", ()):
        if decision.outcome is MappingOutcome.AUTO_MAPPED and decision.target:
            accepted[decision.column_id] = decision.target
    return accepted


def reconcile(state: MigrationState) -> dict[str, Any]:
    """Project rows onto the target shape, then merge them into one record each."""
    targets = _accepted_targets(state)
    files = {source.id: source for source in state.get("files", ())}
    seq = next_sequence(state)

    incoming: list[IncomingRow] = []
    for row in state.get("rows", ()):
        values: dict[str, str | None] = {}
        for column_id, raw in row.values.items():
            if target := targets.get(column_id):
                values[target.value] = raw
        source = files.get(row.file_id)
        incoming.append(
            IncomingRow(
                values=values,
                provenance=Provenance(
                    file_id=row.file_id,
                    file_name=source.name if source else row.file_id,
                    sheet=source.sheet if source else None,
                    row=row.row,
                ),
            )
        )

    result = reconcile_identities(incoming)
    events = [
        _event(
            seq,
            "records_reconciled",
            (
                f"{len(incoming)} source rows became {len(result.records)} records; "
                f"{result.merged_rows} were merged as the same person."
            ),
            source_rows=len(incoming),
            records=len(result.records),
            merged=result.merged_rows,
        )
    ]

    return {
        "records": result.records,
        "issues": result.issues,
        "events": tuple(events),
    }


def _record_resolutions(state: MigrationState) -> tuple[set[str], dict[str, dict[str, str]]]:
    """Reviewer decisions that act on records rather than mappings.

    Returns the records to exclude, and per-record field corrections to apply
    before validation runs again.
    """
    excluded: set[str] = set()
    corrections: dict[str, dict[str, str]] = {}
    issues = {issue.id: issue for issue in state.get("issues", ())}

    for issue_id, choice in state.get("resolutions", {}).items():
        issue = issues.get(issue_id)
        if issue is None or not isinstance(choice, dict) or not issue.record_ids:
            continue

        action = ResolutionAction(choice.get("action", "approve"))
        option_id = str(choice.get("option_id") or "")

        if action is ResolutionAction.EXCLUDE or option_id.startswith("exclude:"):
            target_id = option_id.removeprefix("exclude:") if ":" in option_id else None
            excluded.update({target_id} if target_id else set(issue.record_ids))
            continue

        # A chosen value settles a conflict or replaces an invalid one.
        value: str | None = choice.get("value")
        if value is None and option_id:
            option = next((o for o in issue.options if o.id == option_id), None)
            value = option.value if option else None
        if value is not None and issue.field_name:
            for record_id in issue.record_ids:
                corrections.setdefault(record_id, {})[issue.field_name] = str(value)

    return excluded, corrections


def clean_and_validate(state: MigrationState) -> dict[str, Any]:
    """Apply safe repairs and validate, escalating anything that fails twice."""
    seq = next_sequence(state)
    excluded_ids, corrections = _record_resolutions(state)
    validated: list[CanonicalRecord] = []
    issues: list[ReviewIssue] = []
    events: list[AuditEvent] = []
    repair_count = 0

    for record in state.get("records", ()):
        if record.disposition is Disposition.EXCLUDED or record.id in excluded_ids:
            validated.append(
                record.model_copy(
                    update={
                        "disposition": Disposition.EXCLUDED,
                        "exclusion_reason": record.exclusion_reason or "Excluded by the reviewer.",
                    }
                )
            )
            continue

        values = dict(record.values)
        applied = corrections.get(record.id, {})
        if applied:
            values.update(applied)

        outcome = run_validation_passes(values)
        repair_count += len(outcome.repairs)

        for repair in outcome.repairs:
            spec = get_field(repair.field_name)
            field_label = spec.label if spec else repair.field_name
            rule = repair.rule.replace("_", " ")
            events.append(
                _event(
                    seq,
                    "value_repaired",
                    f"{field_label}: {rule}.",
                    subject=record.values.get("employeeId") or record.id,
                    before=repair.before,
                    after=repair.after,
                )
            )
            seq += 1

        for field_name, new_value in applied.items():
            spec = get_field(field_name)
            events.append(
                _event(
                    seq,
                    "value_corrected",
                    f"Reviewer supplied a {spec.label if spec else field_name}.",
                    actor=Actor.REVIEWER,
                    subject=record.values.get("employeeId") or record.id,
                    before=record.values.get(field_name),
                    after=new_value,
                )
            )
            seq += 1

        disposition = Disposition.READY if outcome.valid else Disposition.NEEDS_REVIEW
        validated.append(
            record.model_copy(
                update={
                    "values": outcome.values,
                    # A human edit produces a new revision, so delivery is bound
                    # to what was actually reviewed.
                    "revision": record.revision + 1 if applied else record.revision,
                    "repairs": outcome.repairs,
                    "validation": outcome.passes,
                    "disposition": disposition,
                }
            )
        )

        if outcome.failed_twice and record.id not in excluded_ids:
            errors: tuple[ValidationError, ...] = outcome.passes[-1].errors
            explanation = (
                "No safe automatic repair existed for this value."
                if outcome.no_repair_available
                else "Safe repairs were applied and it is still invalid."
            )
            invalid_field = errors[0].field_name if errors else None
            spec = get_field(invalid_field) if invalid_field else None
            label = spec.label if spec else (invalid_field or "this value")
            issues.append(
                ReviewIssue(
                    id=f"issue:invalid:{record.id}",
                    type=IssueType.VALIDATION_FAILED_TWICE,
                    reason=(
                        f"{record.values.get('employeeId') or record.id} failed validation "
                        f"twice. {explanation}"
                    ),
                    blocking=True,
                    record_ids=(record.id,),
                    field_name=invalid_field,
                    current_value=(record.values.get(invalid_field) if invalid_field else None),
                    detected_errors=errors,
                    # Never leave a reviewer at a dead end: correcting the value
                    # and excluding the record are the two real ways forward.
                    options=(
                        IssueOption(
                            id="correct_value",
                            label=f"Correct {label}",
                            detail=(
                                f"Supply a valid {label} for this record. "
                                f"It will be validated again."
                            ),
                            value=None,
                        ),
                        IssueOption(
                            id=f"exclude:{record.id}",
                            label="Exclude this record",
                            detail=(
                                "Leave it out of the migration. It stays visible in the "
                                "totals and the audit trail."
                            ),
                        ),
                    ),
                )
            )
            events.append(
                _event(
                    seq,
                    "validation_failed_twice",
                    explanation,
                    subject=record.values.get("employeeId") or record.id,
                    errors=len(errors),
                )
            )
            seq += 1

    ready = sum(1 for r in validated if r.disposition is Disposition.READY)
    events.append(
        _event(
            seq,
            "validation_summary",
            f"{ready} of {len(validated)} records are valid and ready to deliver.",
            ready=ready,
            needs_review=len(validated) - ready,
            repairs=repair_count,
        )
    )

    return {"records": tuple(validated), "issues": tuple(issues), "events": tuple(events)}
