"""Core domain vocabulary shared by the engine, the API and the UI.

These are Pydantic models rather than plain dataclasses because they cross the
HTTP boundary and are persisted in LangGraph checkpoints, so they need
validation and stable serialisation in both directions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from schemabridge.domain.target import ValueKind


def utc_now() -> datetime:
    """Timezone-aware current time. Naive timestamps sort unpredictably."""
    return datetime.now(UTC)


class Frozen(BaseModel):
    """Immutable base. Domain values are replaced, never mutated in place."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Source data and provenance
# ---------------------------------------------------------------------------


class Provenance(Frozen):
    """Where a value came from. Retained for every canonical record."""

    file_id: str
    file_name: str
    sheet: str | None = None
    #: 1-based row number as a person would count it in the source file.
    row: int


class SourceColumn(Frozen):
    """A source column, identified by position so duplicate headers stay distinct."""

    id: str
    file_id: str
    file_name: str
    #: Header text exactly as it appeared.
    header: str
    #: Lowercased, punctuation-stripped header used for alias comparison.
    normalized_header: str
    index: int


class ColumnProfile(Frozen):
    """Aggregate statistics describing one source column."""

    column_id: str
    header: str
    file_name: str
    total_count: int
    non_empty_count: int
    distinct_count: int
    #: Fraction of non-empty values that are unique, 0-1.
    unique_ratio: float
    #: Value shapes detected deterministically.
    detected_kinds: tuple[ValueKind, ...] = ()
    #: Length-capped examples, safe to show a reviewer or send to a model.
    samples: tuple[str, ...] = ()


class SourceKind(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


class SourceFile(Frozen):
    id: str
    name: str
    kind: SourceKind
    sheet: str | None = None
    byte_size: int
    checksum: str
    columns: tuple[SourceColumn, ...]
    row_count: int


class SourceRow(Frozen):
    """One parsed source row: column id to raw string value."""

    id: str
    file_id: str
    row: int
    values: dict[str, str]


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


class MappingBasis(StrEnum):
    EXACT_NAME = "exact_name"
    ALIAS = "alias"
    #: A rule the reviewer approved after an earlier migration asked them. Kept
    #: distinct from ALIAS so the trail can say the engine knew this because it was
    #: taught, rather than because it shipped knowing it.
    LEARNED_ALIAS = "learned_alias"
    MODEL_ASSISTED = "model_assisted"
    HUMAN_CORRECTION = "human_correction"
    UNMAPPED = "unmapped"


class MappingOutcome(StrEnum):
    AUTO_MAPPED = "auto_mapped"
    ESCALATED = "escalated"
    EXCLUDED = "excluded"


class Actor(StrEnum):
    AGENT = "agent"
    REVIEWER = "reviewer"
    SYSTEM = "system"


class MappingCandidate(Frozen):
    """One candidate pairing of a source column with a target field.

    `target` is a plain field name rather than an enum member: the target schema
    is chosen per run, so the set of valid names is not known until then. The
    built-in template's names are still available as `TargetField` constants, and
    since that is a `StrEnum` a comparison against one keeps working.
    """

    column_id: str
    target: str
    basis: MappingBasis
    #: Human-readable evidence. Deliberately not a single score: the reviewer
    #: needs to see why, and a model's self-reported confidence is not a
    #: calibrated probability.
    evidence: tuple[str, ...] = ()
    type_compatible: bool = True


class MappingDecision(Frozen):
    column_id: str
    #: A target field name from the run's schema, or None when nothing fits.
    target: str | None = None
    outcome: MappingOutcome
    basis: MappingBasis
    evidence: tuple[str, ...] = ()
    #: Other plausible targets, shown to the reviewer when escalated.
    alternatives: tuple[MappingCandidate, ...] = ()
    decided_by: Actor = Actor.AGENT
    decided_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Records and validation
# ---------------------------------------------------------------------------


class ValidationError(Frozen):
    field_name: str | None = None
    code: str
    message: str


class ValidationPassLabel(StrEnum):
    AS_MAPPED = "as_mapped"
    AFTER_REPAIR = "after_repair"


class ValidationPass(Frozen):
    label: ValidationPassLabel
    valid: bool
    errors: tuple[ValidationError, ...] = ()
    at: datetime = Field(default_factory=utc_now)


class AppliedRepair(Frozen):
    """A single safe transformation applied to one value."""

    field_name: str
    rule: str
    before: str | None = None
    after: str | None = None


class Disposition(StrEnum):
    CANDIDATE = "candidate"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    EXCLUDED = "excluded"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"


class CanonicalRecord(Frozen):
    id: str
    #: Increments on every human edit; delivery is bound to a specific revision.
    revision: int = 1
    identity_key: str | None = None
    values: dict[str, str | None]
    provenance: tuple[Provenance, ...] = ()
    repairs: tuple[AppliedRepair, ...] = ()
    validation: tuple[ValidationPass, ...] = ()
    disposition: Disposition = Disposition.CANDIDATE
    #: Set when excluded, so totals always reconcile.
    exclusion_reason: str | None = None


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------


class IssueType(StrEnum):
    AMBIGUOUS_MAPPING = "AMBIGUOUS_MAPPING"
    COMPETING_COLUMNS = "COMPETING_COLUMNS"
    REQUIRED_FIELD_UNMAPPED = "REQUIRED_FIELD_UNMAPPED"
    AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    DUPLICATE_EMAIL = "DUPLICATE_EMAIL"
    VALIDATION_FAILED_TWICE = "VALIDATION_FAILED_TWICE"
    UNSAFE_CLEANUP = "UNSAFE_CLEANUP"
    DELIVERY_FAILED = "DELIVERY_FAILED"


class IssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ResolutionAction(StrEnum):
    APPROVE = "approve"
    CORRECT = "correct"
    REJECT = "reject"
    EXCLUDE = "exclude"


class IssueOption(Frozen):
    """A choice the reviewer can pick, rendered as a one-click option."""

    id: str
    label: str
    detail: str
    #: The target field this option would map to, when that is what it decides.
    target: str | None = None
    value: str | None = None


class IssueResolution(Frozen):
    action: ResolutionAction
    option_id: str | None = None
    value: str | None = None
    note: str | None = None
    resolved_by: Actor = Actor.REVIEWER
    resolved_at: datetime = Field(default_factory=utc_now)


class ReviewIssue(Frozen):
    id: str
    type: IssueType
    status: IssueStatus = IssueStatus.OPEN
    #: Plain-language explanation of why the agent stopped.
    reason: str
    #: Whether the run cannot finish until this is resolved.
    blocking: bool = True
    column_id: str | None = None
    field_name: str | None = None
    record_ids: tuple[str, ...] = ()
    current_value: str | None = None
    recommendation: IssueOption | None = None
    options: tuple[IssueOption, ...] = ()
    detected_errors: tuple[ValidationError, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
    resolution: IssueResolution | None = None


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


class DeliveryOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    #: The request was sent but the response was lost. Not the same as failure:
    #: the destination may well have accepted it.
    UNKNOWN = "unknown"


class DeliveryState(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"


class DeliveryAttempt(Frozen):
    attempt: int
    at: datetime = Field(default_factory=utc_now)
    status: int | None = None
    outcome: DeliveryOutcome
    detail: str = ""


class DeliveryIntent(Frozen):
    record_id: str
    #: The record revision frozen when delivery began.
    revision: int
    idempotency_key: str
    payload_hash: str
    attempts: tuple[DeliveryAttempt, ...] = ()
    state: DeliveryState = DeliveryState.PENDING
    target_id: str | None = None
    next_attempt_at: datetime | None = None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class EventExecutionBasis(StrEnum):
    """How the recorded action was carried out, independently of its actor."""

    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"
    HUMAN = "human"
    #: Used for audit events written before execution provenance was recorded.
    UNKNOWN = "unknown"


class AuditEvent(Frozen):
    """One recorded decision. Doubles as the UI's activity feed."""

    #: Monotonic per run; also the polling cursor.
    seq: int
    at: datetime = Field(default_factory=utc_now)
    actor: Actor
    #: How the action was executed. An agent actor can use either policy or a model.
    execution_basis: EventExecutionBasis = EventExecutionBasis.UNKNOWN
    action: str
    #: Why this happened: the policy rule, or the reviewer's choice.
    reason: str
    subject: str | None = None
    before: str | None = None
    after: str | None = None
    detail: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


class RunPhase(StrEnum):
    INGESTED = "ingested"
    ANALYZING = "analyzing"
    REVIEW = "review"
    READY = "ready"
    DELIVERING = "delivering"
    COMPLETE = "complete"
    COMPLETE_WITH_FAILURES = "complete_with_failures"
    #: Infrastructure or configuration failure. Resumable once fixed.
    BLOCKED = "blocked"


TERMINAL_PHASES: frozenset[RunPhase] = frozenset(
    {RunPhase.COMPLETE, RunPhase.COMPLETE_WITH_FAILURES}
)


class RunCounters(Frozen):
    source_rows: int = 0
    canonical_records: int = 0
    merged_rows: int = 0
    auto_mapped_fields: int = 0
    escalated_fields: int = 0
    repairs_applied: int = 0
    model_requests: int = 0
    delivered: int = 0
    failed: int = 0
    excluded: int = 0
