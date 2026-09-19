"""What the model is allowed to look at, and what it is allowed to check.

Both tools are read-only and scoped to one run. The model cannot query the
database, read whole rows, change a mapping, or reach the destination API — it
receives a summary and returns a suggestion, and the application decides what to
do with it.

Prompt content is untrusted. Headers and sample values come from an uploaded
file, so they are treated as data: bounded in size, never interpolated into
instructions that could change the model's task.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemabridge.domain.models import ColumnProfile, SourceColumn
from schemabridge.domain.normalize import detect_value_kinds
from schemabridge.domain.target import TARGET_FIELDS, ValueKind, get_field

#: Compatible value kinds per target kind, mirroring the deterministic policy.
_COMPATIBLE: dict[ValueKind, frozenset[ValueKind]] = {
    ValueKind.IDENTIFIER: frozenset({ValueKind.IDENTIFIER, ValueKind.TEXT}),
    ValueKind.PERSON_NAME: frozenset({ValueKind.PERSON_NAME, ValueKind.TEXT}),
    ValueKind.EMAIL: frozenset({ValueKind.EMAIL}),
    ValueKind.DATE: frozenset({ValueKind.DATE}),
    ValueKind.TEXT: frozenset(
        {ValueKind.TEXT, ValueKind.ENUM, ValueKind.PERSON_NAME, ValueKind.IDENTIFIER}
    ),
    ValueKind.ENUM: frozenset({ValueKind.ENUM, ValueKind.TEXT}),
}

_MAX_SAMPLES = 3
_MAX_SAMPLE_LENGTH = 60


def describe_target_schema() -> str:
    """The target fields, as the model needs to see them."""
    lines = ["Permitted target fields:"]
    for spec in TARGET_FIELDS:
        requirement = "required" if spec.required else "optional"
        detail = f"- {spec.name.value} ({requirement}, {spec.kind.value}): {spec.description}"
        if spec.enum_values:
            detail += f" Allowed values: {', '.join(spec.enum_values)}."
        lines.append(detail)
    return "\n".join(lines)


def describe_columns(columns: list[SourceColumn], profiles: dict[str, ColumnProfile]) -> str:
    """Summarise the columns awaiting a decision.

    Deliberately a profile, not the data: headers, detected shape, how full the
    column is, and a few short examples. The model never sees the dataset.
    """
    lines = ["Source columns needing a mapping:"]
    for column in columns:
        profile = profiles.get(column.id)
        parts = [f'- id={column.id} header="{column.header}"']
        if profile:
            kinds = profile.detected_kinds or tuple(detect_value_kinds(list(profile.samples)))
            shape = kinds[0].value if kinds else "unknown"
            samples = ", ".join(
                (s if len(s) <= _MAX_SAMPLE_LENGTH else f"{s[:_MAX_SAMPLE_LENGTH]}...")
                for s in profile.samples[:_MAX_SAMPLES]
            )
            parts.append(f"shape={shape}")
            parts.append(f"filled={profile.non_empty_count}/{profile.total_count}")
            if samples:
                parts.append(f"examples=[{samples}]")
        lines.append(" ".join(parts))
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class CheckedMapping:
    """The verdict on one proposed mapping."""

    column_id: str
    target: str
    accepted: bool
    evidence: tuple[str, ...]


def check_proposed_mapping(
    column: SourceColumn,
    profile: ColumnProfile | None,
    target: str,
    already_taken: set[str],
) -> CheckedMapping:
    """Verify a proposal against deterministic evidence.

    This is the gate that makes the model advisory. A suggestion is accepted only
    if the target exists, nothing else in the same file already claims it, and the
    column's actual values are compatible with the field's type. Confidence the
    model might express about its own answer plays no part.
    """
    evidence: list[str] = []

    spec = get_field(target)
    if spec is None:
        return CheckedMapping(
            column.id, target, False, (f'"{target}" is not a field in the target schema.',)
        )

    if target in already_taken:
        return CheckedMapping(
            column.id,
            target,
            False,
            (f"{spec.label} is already supplied by another column.",),
        )

    kinds: tuple[ValueKind, ...] = ()
    if profile is not None:
        kinds = profile.detected_kinds or tuple(detect_value_kinds(list(profile.samples)))

    if kinds:
        allowed = _COMPATIBLE[spec.kind]
        if not any(kind in allowed for kind in kinds):
            return CheckedMapping(
                column.id,
                target,
                False,
                (
                    f"Values in this column look like {kinds[0].value}, which is not "
                    f"compatible with {spec.label}.",
                ),
            )
        evidence.append(f"Values look like {kinds[0].value}, which fits {spec.label}.")
    else:
        evidence.append("Column has no values to contradict the suggestion.")

    evidence.append("Model suggestion, confirmed by deterministic checks.")
    return CheckedMapping(column.id, target, True, tuple(evidence))
