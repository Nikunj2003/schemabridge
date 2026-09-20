"""Safe automatic repairs.

"Safe" has a precise meaning: the transformation cannot change what the value
means. Trimming whitespace is safe. Title-casing a name is not, because it
corrupts "McDonald", "van der Berg" and "d'Souza". Guessing a locale for an
ambiguous date is not. Anything failing that test is reported as unrepairable
and escalated instead of applied.

Every rule here is chosen by the field's `ValueKind`, never by its name. That is
what lets a schema nobody wrote code for still get its emails lowercased and its
dates normalised.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from schemabridge.domain.models import AppliedRepair
from schemabridge.domain.normalize import (
    DateParseResult,
    DateStatus,
    parse_calendar_date,
    trim_surrounding,
)
from schemabridge.domain.rules import EMPTY_RULES, DateOrder, RuleSet
from schemabridge.domain.schema import TargetSchema, ValueKind

#: What a record's values are, once this module has produced them.
RecordValues = dict[str, str | None]

#: What a caller may pass in. Wider than `RecordValues` because a dict is
#: invariant in its value type, so a plain `dict[str, str]` — which every literal
#: record in a test is — would otherwise be rejected.
SourceValues = Mapping[str, str | None]


@dataclass(slots=True)
class RepairResult:
    values: RecordValues
    repairs: tuple[AppliedRepair, ...] = ()
    #: Fields that needed fixing but had no safe rule available.
    unrepairable: tuple[str, ...] = field(default_factory=tuple)


_SEPARATORS = re.compile(r"[\s_-]+")


def normalize_enum_value(
    field_name: str, value: str, *, schema: TargetSchema, rules: RuleSet = EMPTY_RULES
) -> str | None:
    """Map a value onto its canonical enum member, or None if unrecognised.

    The accepted spellings come from the field's own `value_aliases`, so a
    user-defined enum canonicalises exactly as the built-in one does. An unlisted
    spelling returns None and escalates: deciding that "Seasonal Temp" means
    "contract" is a business call, not a formatting one — the kind of call a person
    makes once and a learned rule then remembers.

    Order matters here. An exact member wins over everything, because a value that
    already *is* a member needs no translation. A learned rule comes next, ahead of
    the shipped alias table, so approving a rule is how someone disagrees with a
    shipped spelling. And a rule whose canonical value is not a member of this
    field's enum is ignored rather than applied: the rule may predate a schema edit
    that removed it, and writing a non-member would fail validation later with no
    explanation of where the value came from.
    """
    spec = schema.field(field_name)
    if spec is None or spec.kind is not ValueKind.ENUM:
        return None
    normalized = _SEPARATORS.sub("", trim_surrounding(value).lower())
    # An exact member always wins over an alias table that might disagree.
    for member in spec.enum_values:
        if _SEPARATORS.sub("", member.lower()) == normalized:
            return member
    learned = rules.canonical_for(field_name, value)
    if learned is not None and learned.canonical in spec.enum_values:
        return learned.canonical
    return spec.value_aliases.get(normalized)


def _normalize_email(value: str) -> str:
    """Lowercase the domain only: the local part is case-sensitive per RFC."""
    at = value.rfind("@")
    if at <= 0:
        return value
    return value[:at] + "@" + value[at + 1 :].lower()


def _apply_date_rule(
    parsed: DateParseResult,
    rules: RuleSet,
    *,
    header: str,
    field_name: str,
) -> str | None:
    """The reading a learned rule chooses for an ambiguous date, if any.

    Returns None whenever the rule cannot be applied with certainty — no rule, or a
    rule whose chosen reading is not among the interpretations the parser actually
    produced. The second case is not hypothetical: the interpretations depend on the
    value, so a day-first rule has nothing to select in a date whose only valid
    reading is month-first, and that value must stay unrepaired rather than be
    forced.
    """
    rule = rules.date_order_for(header=header, field_name=field_name)
    if rule is None or rule.date_order is None:
        return None
    wanted = "DD/MM/YYYY" if rule.date_order is DateOrder.DAY_FIRST else "MM/DD/YYYY"
    for interpretation in parsed.interpretations:
        if interpretation.format == wanted:
            return interpretation.value
    return None


def apply_safe_repairs(
    source: SourceValues,
    *,
    schema: TargetSchema,
    rules: RuleSet = EMPTY_RULES,
    headers: Mapping[str, str] | None = None,
) -> RepairResult:
    """Apply every safe repair, reporting exactly what changed.

    Idempotent: applying the result again produces no further repairs.

    `headers` maps a field name to the source header it came from, so a date rule
    taught about one column applies only to values that column supplied. Without it
    a date rule is matched by field alone, which is the right fallback but a broader
    one than the person may have intended.
    """
    values: RecordValues = dict(source)
    repairs: list[AppliedRepair] = []
    unrepairable: list[str] = []

    def record(name: str, rule: str, before: str, after: str) -> None:
        if before == after:
            return
        values[name] = after
        repairs.append(AppliedRepair(field_name=name, rule=rule, before=before, after=after))

    for name, raw in source.items():
        if raw is None:
            continue

        # 1. Surrounding whitespace is never meaningful.
        trimmed = trim_surrounding(raw)
        if trimmed != raw:
            record(name, "trim_whitespace", raw, trimmed)
        if not trimmed:
            continue

        spec = schema.field(name)
        if spec is None:
            continue

        if spec.kind is ValueKind.EMAIL:
            record(name, "lowercase_email_domain", trimmed, _normalize_email(trimmed))
        elif spec.kind is ValueKind.DATE:
            parsed = parse_calendar_date(trimmed)
            if parsed.status is DateStatus.PARSED and parsed.value is not None:
                record(name, "normalize_date", trimmed, parsed.value)
            elif parsed.status is DateStatus.AMBIGUOUS:
                # Two readings, both real. A rule is the only thing that may settle
                # this, and only one naming this column or field: guessing a locale
                # is the error this whole module exists to avoid.
                settled = _apply_date_rule(
                    parsed, rules, header=(headers or {}).get(name, ""), field_name=name
                )
                if settled is not None:
                    record(name, "normalize_date_learned", trimmed, settled)
                else:
                    unrepairable.append(name)
            elif parsed.status is DateStatus.INVALID:
                # No safe reading. Leave it exactly as the client wrote it.
                unrepairable.append(name)
        elif spec.kind is ValueKind.ENUM:
            canonical = normalize_enum_value(name, trimmed, schema=schema, rules=rules)
            if canonical is not None:
                record(name, "canonicalize_enum", trimmed, canonical)
            else:
                unrepairable.append(name)
        # Identifiers, names and free text: trimming is the only safe change.
        # Casing and internal punctuation carry meaning we may not rewrite.

    return RepairResult(values=values, repairs=tuple(repairs), unrepairable=tuple(unrepairable))
