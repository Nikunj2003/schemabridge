"""Identity reconciliation: turning rows from several files into one record each.

Merging is intentionally conservative. Two rows merge only when they share an
exact employee ID *and* disagree about nothing. Name similarity is never grounds
for a merge: "Jon Smith" and "John Smith" may well be two people, and silently
collapsing them loses a record with no trace.

Comparison happens on canonical *meaning*, not raw text. "full-time" and
"Permanent" both mean full_time, and "14 March 2026" is the same day as
"2026-03-14" — reporting either as a conflict would put a non-decision in front
of the reviewer. That matters more than it sounds: a queue full of false
conflicts teaches the reviewer to click through, which is exactly how the real
conflict two rows later gets approved without being read.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from schemabridge.domain.cleanup import normalize_enum_value
from schemabridge.domain.models import (
    CanonicalRecord,
    Disposition,
    IssueOption,
    IssueType,
    Provenance,
    ReviewIssue,
    ValidationError,
)
from schemabridge.domain.normalize import (
    DateStatus,
    is_blank,
    parse_calendar_date,
    trim_surrounding,
)
from schemabridge.domain.target import ValueKind, get_field


@dataclass(frozen=True, slots=True)
class IncomingRow:
    values: dict[str, str | None]
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    records: tuple[CanonicalRecord, ...]
    issues: tuple[ReviewIssue, ...]
    merged_rows: int


@dataclass(slots=True)
class _Group:
    key: str | None
    id: str
    values: dict[str, str | None]
    provenance: list[Provenance]
    conflicts: dict[str, set[str]] = field(default_factory=dict)


def _identity_key(values: dict[str, str | None]) -> str | None:
    """Match key for an employee ID: case- and whitespace-insensitive."""
    raw = values.get("employeeId")
    if raw is None:
        return None
    trimmed = trim_surrounding(raw)
    return trimmed.lower() or None


def canonical_meaning(field_name: str, value: str) -> str | None:
    """Reduce a value to what it means, so spellings do not read as conflicts.

    Returns None when there is no safe canonical form — an ambiguous date, or an
    enum spelling outside the vocabulary. None can never be declared equal to
    anything, so genuine uncertainty still reaches a human.
    """
    trimmed = trim_surrounding(value)
    if not trimmed:
        return ""

    spec = get_field(field_name)
    if spec is None:
        return trimmed

    if spec.kind is ValueKind.DATE:
        parsed = parse_calendar_date(trimmed)
        return parsed.value if parsed.status is DateStatus.PARSED else None
    if spec.kind is ValueKind.ENUM:
        return normalize_enum_value(spec.name, trimmed)
    if spec.kind is ValueKind.EMAIL:
        at = trimmed.rfind("@")
        if at <= 0:
            return trimmed
        return trimmed[:at] + "@" + trimmed[at + 1 :].lower()
    return trimmed


def _equivalent(field_name: str, left: str, right: str) -> bool:
    """Whether two values assert the same fact, allowing for spelling."""
    if trim_surrounding(left) == trim_surrounding(right):
        return True
    left_meaning = canonical_meaning(field_name, left)
    right_meaning = canonical_meaning(field_name, right)
    if left_meaning is None or right_meaning is None:
        return False
    return left_meaning == right_meaning


def _group_rows(rows: Sequence[IncomingRow]) -> tuple[list[_Group], int]:
    groups: list[_Group] = []
    by_key: dict[str, _Group] = {}
    merged = 0

    for index, incoming in enumerate(rows):
        key = _identity_key(incoming.values)
        existing = by_key.get(key) if key is not None else None

        if existing is None:
            group = _Group(
                key=key,
                id=f"rec:{key or f'row-{index}'}",
                values=dict(incoming.values),
                provenance=[incoming.provenance],
            )
            groups.append(group)
            if key is not None:
                by_key[key] = group
            continue

        # Same employee, seen again. Combine field by field.
        existing.provenance.append(incoming.provenance)
        merged += 1

        for name, value in incoming.values.items():
            current = existing.values.get(name)

            if is_blank(current) and not is_blank(value):
                # One file simply had a gap the other fills.
                existing.values[name] = value
                continue
            if is_blank(value) or is_blank(current) or current is None or value is None:
                continue
            if _equivalent(name, current, value):
                # Same fact, different spelling. Store the canonical form so the
                # merged record does not depend on which file was read first.
                canonical = canonical_meaning(name, current)
                if canonical:
                    existing.values[name] = canonical
                continue

            # Both files assert a value and they disagree. A human must choose.
            existing.conflicts.setdefault(name, set()).update(
                {trim_surrounding(current), trim_surrounding(value)}
            )

    return groups, merged


def _conflict_issue(group: _Group, field_name: str, observed: Iterable[str]) -> ReviewIssue:
    spec = get_field(field_name)
    label = spec.label if spec else field_name
    values = sorted(observed)
    quoted = " and ".join(f'"{value}"' for value in values)
    return ReviewIssue(
        id=f"issue:conflict:{group.id}:{field_name}",
        type=IssueType.IDENTITY_CONFLICT,
        reason=(
            f"{group.values.get('employeeId') or group.id} appears in "
            f"{len(group.provenance)} places with different values for {label}: "
            f"{quoted}. Merging would silently discard one of them."
        ),
        blocking=True,
        field_name=field_name,
        record_ids=(group.id,),
        current_value=group.values.get(field_name),
        options=tuple(
            IssueOption(
                id=f"value:{value}",
                label=value,
                detail=f'Use "{value}" for {label}.',
                value=value,
            )
            for value in values
        ),
        detected_errors=(
            ValidationError(
                field_name=field_name,
                code="identity_conflict",
                message="Sources disagree: " + " vs ".join(f'"{v}"' for v in values) + ".",
            ),
        ),
    )


def _duplicate_email_issues(records: Sequence[CanonicalRecord]) -> list[ReviewIssue]:
    """One address under two IDs is a strong signal, but not ours to resolve."""
    by_email: dict[str, list[str]] = {}
    for record in records:
        email = record.values.get("workEmail")
        if is_blank(email) or email is None:
            continue
        by_email.setdefault(trim_surrounding(email).lower(), []).append(record.id)

    issues: list[ReviewIssue] = []
    for email, record_ids in by_email.items():
        if len(record_ids) < 2:
            continue
        options: list[IssueOption] = [
            IssueOption(
                id="keep_all",
                label="Keep both records",
                detail="Treat them as genuinely different people and migrate both.",
            )
        ]
        options.extend(
            IssueOption(
                id=f"exclude:{record_id}",
                label=f"Exclude {record_id.removeprefix('rec:')}",
                detail="Leave that record out of this migration.",
            )
            for record_id in record_ids
        )
        issues.append(
            ReviewIssue(
                id=f"issue:dupemail:{email}",
                type=IssueType.DUPLICATE_EMAIL,
                reason=(
                    f"{len(record_ids)} different employee IDs share the work email "
                    f'"{email}". They may be duplicates of one person, or one address '
                    f"may be wrong. The target schema cannot tell these apart."
                ),
                blocking=False,
                field_name="workEmail",
                record_ids=tuple(record_ids),
                current_value=email,
                options=tuple(options),
            )
        )
    return issues


def reconcile_identities(rows: Sequence[IncomingRow]) -> ReconcileResult:
    """Collapse rows into one record per employee, escalating real disagreements."""
    groups, merged_rows = _group_rows(rows)

    issues: list[ReviewIssue] = []
    records: list[CanonicalRecord] = []

    for group in groups:
        for field_name, observed in group.conflicts.items():
            issues.append(_conflict_issue(group, field_name, observed))

        records.append(
            CanonicalRecord(
                id=group.id,
                identity_key=group.key,
                values=dict(group.values),
                provenance=tuple(group.provenance),
                disposition=(
                    Disposition.NEEDS_REVIEW if group.conflicts else Disposition.CANDIDATE
                ),
            )
        )

    issues.extend(_duplicate_email_issues(records))
    return ReconcileResult(records=tuple(records), issues=tuple(issues), merged_rows=merged_rows)
