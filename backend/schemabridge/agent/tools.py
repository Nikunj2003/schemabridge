"""What the model is allowed to look at, and what it is allowed to check.

Both tools are read-only and scoped to one run. The model cannot query the
database, read whole rows, change a mapping, or reach the destination API — it
receives a summary and returns a suggestion, and the application decides what to
do with it.

Prompt content is untrusted. Headers and sample values come from an uploaded
file, so every one of them passes through `agent.sanitize` before it reaches a
prompt: structure neutralised, length capped, invisible characters stripped. See
that module for what this does and does not defend against.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemabridge.agent.config import MAX_PROMPT_SAMPLES
from schemabridge.agent.sanitize import safe_value
from schemabridge.domain.models import ColumnProfile, SourceColumn
from schemabridge.domain.normalize import detect_value_kinds
from schemabridge.domain.schema import TargetSchema, ValueKind, kinds_compatible


def describe_target_schema(schema: TargetSchema, *, exclude: set[str] | None = None) -> str:
    """The target fields, as the model needs to see them.

    Fields already supplied by another column are left out rather than listed and
    forbidden: a field the model cannot see is one it cannot propose, which is
    more reliable than a rule telling it not to.
    """
    taken = exclude or set()
    # Scrubbed like any other prompt content. A schema is authored by its owner
    # rather than uploaded, so this is not the untrusted-file case — but a schema
    # can be imported from a spec file, and a learned rule's rationale is written by
    # the model and shown back to it on a later run. Neither is worth trusting to
    # stay free of prompt structure.
    lines = [f"Target schema: {safe_value(schema.name)}"]
    if schema.description:
        lines.append(safe_value(schema.description))
    lines.append("")
    lines.append("Permitted target fields:")
    for spec in schema.fields:
        if spec.name in taken:
            continue
        requirement = "required" if spec.required else "optional"
        detail = f"- {spec.name} ({requirement}, {spec.kind.value})"
        if spec.description:
            detail += f": {safe_value(spec.description)}"
        if spec.enum_values:
            detail += f" Allowed values: {', '.join(safe_value(v) for v in spec.enum_values)}."
        lines.append(detail)
    if taken:
        lines.append("")
        lines.append(
            "Already supplied by another column, so not available: "
            + ", ".join(sorted(taken))
            + "."
        )
    return "\n".join(lines)


def describe_columns(columns: list[SourceColumn], profiles: dict[str, ColumnProfile]) -> str:
    """Summarise the columns awaiting a decision.

    Deliberately a profile, not the data: headers, detected shape, how full the
    column is, how many distinct values it holds, and a few short examples. The
    model never sees the dataset.

    Fill rate and distinctness are included because they are the evidence that
    contradicts a header. A column called "Employee ID" that is 4% filled, or one
    holding three distinct values across two hundred rows, is not an identifier
    whatever it is called — and saying so is more useful than asking the model to
    trust the name.
    """
    lines = ["Source columns needing a mapping:"]
    for column in columns:
        profile = profiles.get(column.id)
        parts = [f"- id={column.id} header={safe_value(column.header)}"]
        if profile:
            kinds = profile.detected_kinds or tuple(detect_value_kinds(list(profile.samples)))
            parts.append(f"shape={kinds[0].value if kinds else 'unknown'}")
            parts.append(f"filled={profile.non_empty_count}/{profile.total_count}")
            parts.append(f"distinct={profile.distinct_count}")
            samples = ", ".join(safe_value(s) for s in profile.samples[:MAX_PROMPT_SAMPLES])
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
    *,
    schema: TargetSchema,
) -> CheckedMapping:
    """Verify a proposal against deterministic evidence.

    This is the gate that makes the model advisory. A suggestion is accepted only
    if the target exists, nothing else in the same file already claims it, and the
    column's actual values are compatible with the field's type. Confidence the
    model might express about its own answer plays no part.
    """
    evidence: list[str] = []

    spec = schema.field(target)
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
        # The same table the deterministic gates use, so the verifier cannot be
        # more permissive than the policy it is standing in for.
        if not kinds_compatible(spec.kind, kinds):
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
