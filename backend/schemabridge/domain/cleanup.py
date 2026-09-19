"""Safe automatic repairs.

"Safe" has a precise meaning: the transformation cannot change what the value
means. Trimming whitespace is safe. Title-casing a name is not, because it
corrupts "McDonald", "van der Berg" and "d'Souza". Guessing a locale for an
ambiguous date is not. Anything failing that test is reported as unrepairable
and escalated instead of applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from schemabridge.domain.models import AppliedRepair
from schemabridge.domain.normalize import DateStatus, parse_calendar_date, trim_surrounding
from schemabridge.domain.target import TargetField, ValueKind, get_field

RecordValues = dict[str, str | None]


@dataclass(slots=True)
class RepairResult:
    values: RecordValues
    repairs: tuple[AppliedRepair, ...] = ()
    #: Fields that needed fixing but had no safe rule available.
    unrepairable: tuple[str, ...] = field(default_factory=tuple)


#: Accepted spellings per enum vocabulary. Explicit by design: an unlisted
#: spelling is escalated rather than fuzzy-matched, because deciding that
#: "Seasonal Temp" means "contract" is a business decision, not a formatting one.
_ENUM_ALIASES: dict[str, dict[str, str]] = {
    TargetField.EMPLOYMENT_TYPE.value: {
        "fulltime": "full_time",
        "full": "full_time",
        "permanent": "full_time",
        "fte": "full_time",
        "regular": "full_time",
        "parttime": "part_time",
        "part": "part_time",
        "contract": "contract",
        "contractor": "contract",
        "contractual": "contract",
        "temporary": "contract",
        "temp": "contract",
        "fixedterm": "contract",
        "intern": "intern",
        "internship": "intern",
        "trainee": "intern",
        "apprentice": "intern",
    }
}

_SEPARATORS = re.compile(r"[\s_-]+")


def normalize_enum_value(field_name: TargetField | str, value: str) -> str | None:
    """Map a value onto its canonical enum member, or None if unrecognised."""
    key = field_name.value if isinstance(field_name, TargetField) else field_name
    table = _ENUM_ALIASES.get(key)
    if table is None:
        return None
    normalized = _SEPARATORS.sub("", trim_surrounding(value).lower())
    return table.get(normalized)


def _normalize_email(value: str) -> str:
    """Lowercase the domain only: the local part is case-sensitive per RFC."""
    at = value.rfind("@")
    if at <= 0:
        return value
    return value[:at] + "@" + value[at + 1 :].lower()


def apply_safe_repairs(source: RecordValues) -> RepairResult:
    """Apply every safe repair, reporting exactly what changed.

    Idempotent: applying the result again produces no further repairs.
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

        spec = get_field(name)
        if spec is None:
            continue

        if spec.kind is ValueKind.EMAIL:
            record(name, "lowercase_email_domain", trimmed, _normalize_email(trimmed))
        elif spec.kind is ValueKind.DATE:
            parsed = parse_calendar_date(trimmed)
            if parsed.status is DateStatus.PARSED and parsed.value is not None:
                record(name, "normalize_date", trimmed, parsed.value)
            elif parsed.status in {DateStatus.AMBIGUOUS, DateStatus.INVALID}:
                # No safe reading. Leave it exactly as the client wrote it.
                unrepairable.append(name)
        elif spec.kind is ValueKind.ENUM:
            canonical = normalize_enum_value(spec.name, trimmed)
            if canonical is not None:
                record(name, "canonicalize_enum", trimmed, canonical)
            else:
                unrepairable.append(name)
        # Identifiers, names and free text: trimming is the only safe change.
        # Casing and internal punctuation carry meaning we may not rewrite.

    return RepairResult(values=values, repairs=tuple(repairs), unrepairable=tuple(unrepairable))
