"""The workflow's state, and how concurrent updates to it combine.

Reducers matter here. A resumed run re-enters the graph with whatever the
checkpointer persisted, so anything append-only — audit events, applied
mappings, delivery attempts — must accumulate rather than be replaced. Getting
that wrong loses the record of what the engine already did, which is precisely
what the audit trail exists to prevent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, TypedDict

from schemabridge.domain.models import (
    AuditEvent,
    CanonicalRecord,
    ColumnProfile,
    DeliveryIntent,
    MappingDecision,
    ReviewIssue,
    RunPhase,
    SourceColumn,
    SourceFile,
    SourceRow,
)
from schemabridge.domain.schema import TargetSchema


def append[T](existing: Sequence[T] | None, incoming: Sequence[T] | T | None) -> tuple[T, ...]:
    """Append-only channel reducer.

    Written explicitly rather than using `operator.add` because the checkpointer
    round-trips these values, and a channel can therefore be handed a list where
    it last held a tuple. `operator.add` raises on that mix; normalising both
    sides keeps a resumed run working.
    """
    current: tuple[T, ...] = tuple(existing) if existing else ()
    if incoming is None:
        return current
    if isinstance(incoming, str | bytes) or not isinstance(incoming, Sequence):
        return (*current, incoming)
    return (*current, *incoming)


def replace_records(
    _existing: Sequence[CanonicalRecord] | None, incoming: Sequence[CanonicalRecord]
) -> tuple[CanonicalRecord, ...]:
    """Records are recomputed wholesale after a correction, so replace them.

    Appending would leave stale revisions alongside the corrected ones, and the
    UI would show both.
    """
    return tuple(incoming)


def merge_issues(
    existing: Sequence[ReviewIssue] | None, incoming: Sequence[ReviewIssue]
) -> tuple[ReviewIssue, ...]:
    """Merge by id, preserving any resolution the reviewer already supplied.

    Nodes downstream of review re-derive their issues, so `reconcile` and
    `clean_and_validate` re-emit a fresh copy of the same id on every pass. If
    the incoming copy simply won, a resolved issue would silently reopen and the
    reviewer would be asked the same question forever. A resolution is therefore
    sticky: only its detail is refreshed.
    """
    by_id = {issue.id: issue for issue in (existing or ())}
    for issue in incoming:
        previous = by_id.get(issue.id)
        if previous is not None and previous.resolution is not None:
            # Keep the decision and the status; take updated context.
            by_id[issue.id] = issue.model_copy(
                update={"status": previous.status, "resolution": previous.resolution}
            )
        else:
            by_id[issue.id] = issue
    return tuple(by_id.values())


def merge_deliveries(
    existing: Sequence[DeliveryIntent] | None, incoming: Sequence[DeliveryIntent]
) -> tuple[DeliveryIntent, ...]:
    """Merge by record id: the latest attempt history for a record wins."""
    by_record = {intent.record_id: intent for intent in (existing or ())}
    for intent in incoming:
        by_record[intent.record_id] = intent
    return tuple(by_record.values())


class MigrationState(TypedDict, total=False):
    """Everything the workflow carries between steps.

    Persisted by the checkpointer, so every value must round-trip through
    serialisation. Pydantic models handle that; raw objects would not.
    """

    # --- Identity and configuration -------------------------------------
    run_id: str
    owner_session_id: str
    policy_version: str
    #: The contract this run maps onto, snapshotted at creation rather than
    #: referenced by id. Editing a saved schema must not change what a paused run
    #: is validated against: a migration's contract is fixed when it starts.
    target_schema: TargetSchema

    # --- Source data ----------------------------------------------------
    files: tuple[SourceFile, ...]
    columns: tuple[SourceColumn, ...]
    rows: tuple[SourceRow, ...]
    profiles: tuple[ColumnProfile, ...]

    # --- Decisions ------------------------------------------------------
    #: Append-only: a resumed run must not lose mappings already applied.
    mappings: Annotated[tuple[MappingDecision, ...], append]
    #: Columns with no deterministic answer, offered to the model.
    unresolved_columns: tuple[str, ...]
    #: Reviewer choices, keyed by issue id, so a resume knows what was decided.
    resolutions: dict[str, Any]

    # --- Results --------------------------------------------------------
    records: Annotated[tuple[CanonicalRecord, ...], replace_records]
    issues: Annotated[tuple[ReviewIssue, ...], merge_issues]
    deliveries: Annotated[tuple[DeliveryIntent, ...], merge_deliveries]

    # --- Observability --------------------------------------------------
    #: Append-only and monotonic. Doubles as the UI's polling cursor.
    events: Annotated[tuple[AuditEvent, ...], append]
    phase: RunPhase
    #: Set when the run cannot continue for an infrastructure reason.
    blocked_reason: str | None
    #: Upstream model requests already spent, enforced against the budget.
    model_requests: int
    #: Origin for outbound delivery, captured from the serving request when no
    #: fixed origin is configured. Never taken from a client-supplied header.
    request_origin: str | None
    #: Per-employee demo behaviour for the destination stub, keyed by employee
    #: id. Configured by the run so production logic carries no test branches.
    demo_delivery: dict[str, str]


def next_sequence(state: MigrationState) -> int:
    """The next audit sequence number for this run."""
    events = state.get("events", ())
    return (max((event.seq for event in events), default=0)) + 1


def run_schema(state: MigrationState) -> TargetSchema:
    """The contract this run maps onto.

    Falls back to the built-in template for a run checkpointed before schemas
    became part of the state, so an in-flight migration is not stranded by the
    upgrade. A checkpoint that round-tripped through a serializer without the
    type registered comes back as a plain dict, so that case is revived too
    rather than crashing on attribute access.
    """
    from schemabridge.domain.target import BUILTIN_SCHEMA

    # Typed as Any deliberately: the annotation promises a TargetSchema, but a
    # checkpoint written before this field existed has nothing, and one that
    # round-tripped through a serializer lacking the type comes back as a plain
    # dict. Both are real states to survive, so the check is a runtime one.
    stored: Any = state.get("target_schema")
    if isinstance(stored, TargetSchema):
        return stored
    if isinstance(stored, dict):
        try:
            return TargetSchema.model_validate(stored)
        except Exception:
            return BUILTIN_SCHEMA
    return BUILTIN_SCHEMA
