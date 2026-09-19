"""Identity reconciliation: turning rows from several files into one record each.

Merging is intentionally conservative. Two rows merge only when they share an
exact employee ID *and* disagree about nothing. Name similarity is never grounds
for a merge: "Jon Smith" and "John Smith" may well be two people, and silently
collapsing them loses a record with no trace.

Which field identifies a record, and which fields must be unique, come from the
schema's own `is_identity` and `is_unique` flags rather than from a hardcoded
`employeeId`. Never inferred from the data: a column that happens to hold
distinct values in one upload is not thereby an identifier, and guessing wrong
either merges two people or splits one.

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
from schemabridge.domain.schema import TargetSchema, ValueKind


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


def _identity_key(values: dict[str, str | None], schema: TargetSchema) -> str | None:
    """Match key for the schema's identity field: case- and space-insensitive.

    None when the schema names no identity field, or the row leaves it blank. In
    either case every row stands alone, which is the safe default: not merging
    keeps a record the reviewer can still see.
    """
    name = schema.identity_field
    if name is None:
        return None
    raw = values.get(name)
    if raw is None:
        return None
    trimmed = trim_surrounding(raw)
    return trimmed.lower() or None


def _subject(group: _Group, schema: TargetSchema) -> str:
    """How to name a record to a person, by whatever the schema names it best."""
    name = schema.naming_field
    if name and (value := group.values.get(name)):
        return value
    return group.id


def canonical_meaning(field_name: str, value: str, *, schema: TargetSchema) -> str | None:
    """Reduce a value to what it means, so spellings do not read as conflicts.

    Returns None when there is no safe canonical form — an ambiguous date, or an
    enum spelling outside the vocabulary. None can never be declared equal to
    anything, so genuine uncertainty still reaches a human.
    """
    trimmed = trim_surrounding(value)
    if not trimmed:
        return ""

    spec = schema.field(field_name)
    if spec is None:
        return trimmed

    if spec.kind is ValueKind.DATE:
        parsed = parse_calendar_date(trimmed)
        return parsed.value if parsed.status is DateStatus.PARSED else None
    if spec.kind is ValueKind.ENUM:
        return normalize_enum_value(spec.name, trimmed, schema=schema)
    if spec.kind is ValueKind.EMAIL:
        at = trimmed.rfind("@")
        if at <= 0:
            return trimmed
        return trimmed[:at] + "@" + trimmed[at + 1 :].lower()
    return trimmed


def _equivalent(field_name: str, left: str, right: str, schema: TargetSchema) -> bool:
    """Whether two values assert the same fact, allowing for spelling."""
    if trim_surrounding(left) == trim_surrounding(right):
        return True
    left_meaning = canonical_meaning(field_name, left, schema=schema)
    right_meaning = canonical_meaning(field_name, right, schema=schema)
    if left_meaning is None or right_meaning is None:
        return False
    return left_meaning == right_meaning


def _group_rows(rows: Sequence[IncomingRow], schema: TargetSchema) -> tuple[list[_Group], int]:
    groups: list[_Group] = []
    by_key: dict[str, _Group] = {}
    merged = 0

    for index, incoming in enumerate(rows):
        key = _identity_key(incoming.values, schema)
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
            if _equivalent(name, current, value, schema):
                # Same fact, different spelling. Store the canonical form so the
                # merged record does not depend on which file was read first.
                canonical = canonical_meaning(name, current, schema=schema)
                if canonical:
                    existing.values[name] = canonical
                continue

            # Both files assert a value and they disagree. A human must choose.
            existing.conflicts.setdefault(name, set()).update(
                {trim_surrounding(current), trim_surrounding(value)}
            )

    return groups, merged


def _conflict_issue(
    group: _Group, field_name: str, observed: Iterable[str], schema: TargetSchema
) -> ReviewIssue:
    spec = schema.field(field_name)
    label = spec.label if spec else field_name
    values = sorted(observed)
    quoted = " and ".join(f'"{value}"' for value in values)
    return ReviewIssue(
        id=f"issue:conflict:{group.id}:{field_name}",
        type=IssueType.IDENTITY_CONFLICT,
        reason=(
            f"{_subject(group, schema)} appears in "
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


def _duplicate_value_issues(
    records: Sequence[CanonicalRecord], schema: TargetSchema
) -> list[ReviewIssue]:
    """Two records sharing a value the schema says should be unique.

    A strong signal, but not ours to resolve: the same address under two ids is
    either one person entered twice or one address typed wrong, and nothing in the
    data distinguishes those. Non-blocking, because guessing would be worse than
    delivering both and letting someone look.
    """
    issues: list[ReviewIssue] = []

    for name in schema.unique_fields:
        spec = schema.field(name)
        label = spec.label if spec else name
        identity_label = name
        if identity := schema.identity_field:
            identity_spec = schema.field(identity)
            identity_label = identity_spec.label if identity_spec else identity

        grouped: dict[str, list[str]] = {}
        for record in records:
            raw = record.values.get(name)
            if is_blank(raw) or raw is None:
                continue
            # Compared on meaning, so "A@x.com" and "a@X.com" count as one.
            canonical = canonical_meaning(name, raw, schema=schema)
            if canonical is None or not canonical:
                continue
            grouped.setdefault(canonical.lower(), []).append(record.id)

        for value, record_ids in grouped.items():
            if len(record_ids) < 2:
                continue
            options: list[IssueOption] = [
                IssueOption(
                    id="keep_all",
                    label="Keep both records",
                    detail="Treat them as genuinely different and migrate both.",
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
                    id=f"issue:duplicate:{name}:{value}",
                    type=IssueType.DUPLICATE_EMAIL,
                    reason=(
                        f"{len(record_ids)} records with different "
                        f'{identity_label} values share the {label} "{value}". They may '
                        f"be duplicates of one record, or one value may be wrong. The "
                        f"target schema cannot tell these apart."
                    ),
                    blocking=False,
                    field_name=name,
                    record_ids=tuple(record_ids),
                    current_value=value,
                    options=tuple(options),
                )
            )
    return issues


def reconcile_identities(rows: Sequence[IncomingRow], *, schema: TargetSchema) -> ReconcileResult:
    """Collapse rows into one record per identity, escalating real disagreements."""
    groups, merged_rows = _group_rows(rows, schema)

    issues: list[ReviewIssue] = []
    records: list[CanonicalRecord] = []

    for group in groups:
        for field_name, observed in group.conflicts.items():
            issues.append(_conflict_issue(group, field_name, observed, schema))

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

    issues.extend(_duplicate_value_issues(records, schema))
    return ReconcileResult(records=tuple(records), issues=tuple(issues), merged_rows=merged_rows)
