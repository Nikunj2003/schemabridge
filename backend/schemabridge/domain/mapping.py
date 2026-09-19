"""Mapping policy: which source column becomes which target field, and whether
the engine may decide that on its own.

There is deliberately no single weighted confidence score. A blended number
hides *why* a decision was made, cannot be explained to a reviewer, and invites
treating an arbitrary threshold as a calibrated probability. Every column passes
through explicit gates instead, and the evidence that opened or closed each gate
is recorded verbatim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from schemabridge.domain.models import (
    ColumnProfile,
    IssueOption,
    IssueType,
    MappingBasis,
    MappingCandidate,
    MappingDecision,
    MappingOutcome,
    ReviewIssue,
    SourceColumn,
)
from schemabridge.domain.normalize import detect_value_kinds
from schemabridge.domain.target import (
    REQUIRED_FIELDS,
    TARGET_FIELDS,
    TargetField,
    TargetFieldSpec,
    ValueKind,
    get_field,
)

POLICY_VERSION = "mapping/1"

#: Value kinds acceptable as evidence for each target kind.
_COMPATIBLE_KINDS: dict[ValueKind, frozenset[ValueKind]] = {
    ValueKind.IDENTIFIER: frozenset({ValueKind.IDENTIFIER, ValueKind.TEXT}),
    ValueKind.PERSON_NAME: frozenset({ValueKind.PERSON_NAME, ValueKind.TEXT}),
    ValueKind.EMAIL: frozenset({ValueKind.EMAIL}),
    ValueKind.DATE: frozenset({ValueKind.DATE}),
    ValueKind.TEXT: frozenset(
        {ValueKind.TEXT, ValueKind.ENUM, ValueKind.PERSON_NAME, ValueKind.IDENTIFIER}
    ),
    ValueKind.ENUM: frozenset({ValueKind.ENUM, ValueKind.TEXT}),
}

#: Headers that name a concept more than one target field shares, so the header
#: alone cannot settle which was meant.
_AMBIGUOUS_HEADERS: dict[str, tuple[TargetField, ...]] = {
    "date": (TargetField.START_DATE, TargetField.END_DATE),
    "dates": (TargetField.START_DATE, TargetField.END_DATE),
    "employmentdate": (TargetField.START_DATE, TargetField.END_DATE),
    "effectivedate": (TargetField.START_DATE, TargetField.END_DATE),
    "contractdate": (TargetField.START_DATE, TargetField.END_DATE),
}


@dataclass(frozen=True, slots=True)
class MappingResult:
    decisions: tuple[MappingDecision, ...]
    issues: tuple[ReviewIssue, ...]
    #: Columns with no deterministic answer, eligible for model assistance.
    unresolved: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    spec: TargetFieldSpec
    basis: MappingBasis
    evidence: tuple[str, ...]
    type_compatible: bool


def _profile_kinds(profile: ColumnProfile) -> tuple[ValueKind, ...]:
    if profile.detected_kinds:
        return profile.detected_kinds
    return tuple(detect_value_kinds(list(profile.samples)))


def _is_type_compatible(spec: TargetFieldSpec, kinds: Sequence[ValueKind]) -> bool:
    if not kinds:
        return True  # No values to contradict the header.
    allowed = _COMPATIBLE_KINDS[spec.kind]
    return any(kind in allowed for kind in kinds)


def _candidates_for(column: SourceColumn, profile: ColumnProfile | None) -> list[_Candidate]:
    """Every target field whose name or aliases match this column's header."""
    kinds = _profile_kinds(profile) if profile else ()
    candidates: list[_Candidate] = []

    for spec in TARGET_FIELDS:
        evidence: list[str] = []
        basis: MappingBasis | None = None

        if column.normalized_header == spec.name.value.lower():
            basis = MappingBasis.EXACT_NAME
            evidence.append(f'Header "{column.header}" is the target field name.')
        elif column.normalized_header in spec.aliases:
            basis = MappingBasis.ALIAS
            evidence.append(f'Header "{column.header}" is a known spelling of {spec.label}.')

        if basis is None:
            continue

        compatible = _is_type_compatible(spec, kinds)
        if compatible:
            evidence.append(
                f"Values look like {kinds[0].value}, which fits {spec.label}."
                if kinds
                else "Column has no values to contradict the header."
            )
        else:
            evidence.append(f"Values look like {kinds[0].value}, which does not fit {spec.label}.")

        candidates.append(
            _Candidate(
                spec=spec,
                basis=basis,
                evidence=tuple(evidence),
                type_compatible=compatible,
            )
        )

    return candidates


def _as_candidate(column_id: str, candidate: _Candidate) -> MappingCandidate:
    return MappingCandidate(
        column_id=column_id,
        target=candidate.spec.name,
        basis=candidate.basis,
        evidence=candidate.evidence,
        type_compatible=candidate.type_compatible,
    )


def _map_option(spec: TargetFieldSpec, header: str) -> IssueOption:
    return IssueOption(
        id=f"map:{spec.name.value}",
        label=f"Map to {spec.label}",
        detail=f'Treat "{header}" as {spec.description}',
        target=spec.name,
    )


def _ignore_option(header: str) -> IssueOption:
    return IssueOption(
        id="ignore",
        label="Ignore this column",
        detail=f'Leave "{header}" out of the migration entirely.',
    )


def _find_contention(
    columns: Sequence[SourceColumn], per_column: dict[str, list[_Candidate]]
) -> tuple[dict[str, list[SourceColumn]], set[str]]:
    """Group columns that contend for the same target *within one file*.

    Columns in different files landing on the same target is reconciliation —
    exactly what multi-file ingestion is for — so only same-file contention is a
    genuine ambiguity.
    """
    contention: dict[str, list[SourceColumn]] = {}
    for column in columns:
        viable = [c for c in per_column.get(column.id, []) if c.type_compatible]
        if len(viable) == 1 and column.normalized_header not in _AMBIGUOUS_HEADERS:
            key = f"{column.file_id}:{viable[0].spec.name.value}"
            contention.setdefault(key, []).append(column)

    contended = {
        column.id for columns_ in contention.values() if len(columns_) > 1 for column in columns_
    }
    return contention, contended


def decide_mappings(
    columns: Sequence[SourceColumn], profiles: Sequence[ColumnProfile]
) -> MappingResult:
    """Decide the mapping for every source column."""
    profile_by_id = {profile.column_id: profile for profile in profiles}
    per_column = {
        column.id: _candidates_for(column, profile_by_id.get(column.id)) for column in columns
    }

    decisions: list[MappingDecision] = []
    issues: list[ReviewIssue] = []
    unresolved: list[str] = []

    contention, contended = _find_contention(columns, per_column)

    for key, competing in contention.items():
        if len(competing) < 2:
            continue
        target = TargetField(key.split(":", 1)[1])
        spec = get_field(target.value)
        assert spec is not None
        headers = ", ".join(f'"{c.header}"' for c in competing)
        issues.append(
            ReviewIssue(
                id=f"issue:competing:{key}",
                type=IssueType.COMPETING_COLUMNS,
                reason=(
                    f"{len(competing)} columns in {competing[0].file_name} could each be "
                    f"{spec.label}: {headers}. Only one can supply it, and the headers do "
                    f"not say which."
                ),
                blocking=spec.required,
                field_name=target.value,
                options=tuple(
                    IssueOption(
                        id=f"use:{c.id}",
                        label=f'Use "{c.header}"',
                        detail=f'Map "{c.header}" to {spec.label} and ignore the others.',
                        target=target,
                    )
                    for c in competing
                ),
            )
        )

    for column in columns:
        candidates = per_column[column.id]
        viable = [c for c in candidates if c.type_compatible]
        profile = profile_by_id.get(column.id)
        sample = profile.samples[0] if profile and profile.samples else None

        # Gate: a header naming a concept several targets share.
        if ambiguous := _AMBIGUOUS_HEADERS.get(column.normalized_header):
            specs = [spec for target in ambiguous if (spec := get_field(target.value))]
            labels = " or ".join(spec.label for spec in specs)
            decisions.append(
                MappingDecision(
                    column_id=column.id,
                    target=None,
                    outcome=MappingOutcome.ESCALATED,
                    basis=MappingBasis.UNMAPPED,
                    evidence=(
                        f'Header "{column.header}" names a concept shared by '
                        f"{' and '.join(spec.label for spec in specs)}.",
                    ),
                    alternatives=tuple(
                        MappingCandidate(
                            column_id=column.id,
                            target=spec.name,
                            basis=MappingBasis.ALIAS,
                            evidence=(f'"{column.header}" could mean {spec.label}.',),
                        )
                        for spec in specs
                    ),
                )
            )
            issues.append(
                ReviewIssue(
                    id=f"issue:ambiguous:{column.id}",
                    type=IssueType.AMBIGUOUS_MAPPING,
                    reason=(
                        f'"{column.header}" in {column.file_name} could be {labels}. '
                        f"The header does not say which, and picking wrong would "
                        f"silently misdate every record in this file."
                    ),
                    blocking=True,
                    column_id=column.id,
                    current_value=sample,
                    options=(
                        *[_map_option(spec, column.header) for spec in specs],
                        _ignore_option(column.header),
                    ),
                )
            )
            continue

        # Gate: another column in the same file claims this target.
        if column.id in contended:
            decisions.append(
                MappingDecision(
                    column_id=column.id,
                    target=None,
                    outcome=MappingOutcome.ESCALATED,
                    basis=MappingBasis.UNMAPPED,
                    evidence=(
                        f"Another column in {column.file_name} claims the same target field.",
                    ),
                    alternatives=tuple(_as_candidate(column.id, c) for c in candidates),
                )
            )
            continue

        # Gate: exactly one type-compatible candidate — act without asking.
        if len(viable) == 1:
            chosen = viable[0]
            decisions.append(
                MappingDecision(
                    column_id=column.id,
                    target=chosen.spec.name,
                    outcome=MappingOutcome.AUTO_MAPPED,
                    basis=chosen.basis,
                    evidence=chosen.evidence,
                )
            )
            continue

        # Gate: several plausible targets — a real decision for a human.
        if len(viable) > 1:
            labels = " and ".join(c.spec.label for c in viable)
            decisions.append(
                MappingDecision(
                    column_id=column.id,
                    target=None,
                    outcome=MappingOutcome.ESCALATED,
                    basis=MappingBasis.UNMAPPED,
                    evidence=(
                        f'"{column.header}" matches {len(viable)} target fields: '
                        f"{', '.join(c.spec.label for c in viable)}.",
                    ),
                    alternatives=tuple(_as_candidate(column.id, c) for c in viable),
                )
            )
            issues.append(
                ReviewIssue(
                    id=f"issue:ambiguous:{column.id}",
                    type=IssueType.AMBIGUOUS_MAPPING,
                    reason=(
                        f'"{column.header}" in {column.file_name} could be {labels}, '
                        f"and matches both equally well."
                    ),
                    blocking=any(c.spec.required for c in viable),
                    column_id=column.id,
                    current_value=sample,
                    options=(
                        *[_map_option(c.spec, column.header) for c in viable],
                        _ignore_option(column.header),
                    ),
                )
            )
            continue

        # Gate: the header matched but the values contradict it.
        if candidates:
            best = candidates[0]
            decisions.append(
                MappingDecision(
                    column_id=column.id,
                    target=None,
                    outcome=MappingOutcome.ESCALATED,
                    basis=MappingBasis.UNMAPPED,
                    evidence=best.evidence,
                    alternatives=tuple(_as_candidate(column.id, c) for c in candidates),
                )
            )
            issues.append(
                ReviewIssue(
                    id=f"issue:mismatch:{column.id}",
                    type=IssueType.AMBIGUOUS_MAPPING,
                    reason=(
                        f'"{column.header}" in {column.file_name} looks like '
                        f"{best.spec.label} by name, but its values do not match that "
                        f"shape. Applying it could corrupt the field."
                    ),
                    blocking=best.spec.required,
                    column_id=column.id,
                    current_value=sample,
                    options=(
                        _map_option(best.spec, column.header),
                        _ignore_option(column.header),
                    ),
                )
            )
            continue

        # No deterministic answer at all. Eligible for model assistance.
        unresolved.append(column.id)
        decisions.append(
            MappingDecision(
                column_id=column.id,
                target=None,
                outcome=MappingOutcome.ESCALATED,
                basis=MappingBasis.UNMAPPED,
                evidence=(f'No known target field matches "{column.header}".',),
            )
        )

    # Required targets nobody supplies.
    supplied = {d.target for d in decisions if d.outcome is MappingOutcome.AUTO_MAPPED}
    offered = {alt.target for d in decisions for alt in d.alternatives}
    for required in REQUIRED_FIELDS:
        if required in supplied or required in offered or unresolved:
            continue
        spec = get_field(required.value)
        assert spec is not None
        issues.append(
            ReviewIssue(
                id=f"issue:missing:{required.value}",
                type=IssueType.REQUIRED_FIELD_UNMAPPED,
                reason=(
                    f"{spec.label} is required by the target schema, but none of the "
                    f"uploaded columns look like it. Records cannot be delivered "
                    f"without it."
                ),
                blocking=True,
                field_name=required.value,
                options=tuple(
                    IssueOption(
                        id=f"use:{c.id}",
                        label=f'Use "{c.header}"',
                        detail=f'Map "{c.header}" from {c.file_name} to {spec.label}.',
                        target=required,
                    )
                    for c in columns
                ),
            )
        )

    return MappingResult(
        decisions=tuple(decisions), issues=tuple(issues), unresolved=tuple(unresolved)
    )


def is_applied(decision: MappingDecision) -> bool:
    """Whether a decision supplies a usable target field."""
    return decision.outcome is MappingOutcome.AUTO_MAPPED and decision.target is not None


__all__ = ["POLICY_VERSION", "MappingResult", "decide_mappings", "is_applied"]
