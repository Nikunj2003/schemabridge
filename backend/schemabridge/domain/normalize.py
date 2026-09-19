"""Deterministic value handling: headers, dates, and value shapes.

Everything here is pure, so the mapping policy can be tested without a database
or a model.

The date rules are deliberately narrow. `dateutil.parser` and similar helpers
guess a locale and accept nonsense, which is precisely the class of error a
migration must not make: reading 03/04/2026 as 4 March when the client meant
3 April is invisible until someone's payroll is wrong. A value with more than
one valid reading is reported as ambiguous and escalated to a human instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Final

from schemabridge.domain.target import ValueKind

_BOM: Final = "﻿"
_NON_ALPHANUMERIC: Final = re.compile(r"[^a-z0-9]+")


def normalize_header(header: str) -> str:
    """Reduce a header to a comparison key: lowercase, alphanumeric only.

    "Employee ID", "employee_id" and "EMPLOYEE.ID" all become "employeeid", so
    the alias tables stay small and readable.
    """
    return _NON_ALPHANUMERIC.sub("", header.replace(_BOM, "").strip().lower())


def trim_surrounding(value: str) -> str:
    """Strip surrounding whitespace only. Internal spacing can be meaningful."""
    return value.replace(_BOM, "").strip()


def is_blank(value: str | None) -> bool:
    """Whether a value carries no content."""
    return value is None or value.strip() == ""


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


class DateStatus(StrEnum):
    EMPTY = "empty"
    PARSED = "parsed"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class DateInterpretation:
    """One possible reading of a date, and how the digits were understood."""

    value: str
    format: str


@dataclass(frozen=True, slots=True)
class DateParseResult:
    status: DateStatus
    value: str | None = None
    format: str | None = None
    interpretations: tuple[DateInterpretation, ...] = field(default_factory=tuple)
    reason: str | None = None


_MONTH_NAMES: Final[dict[str, int]] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}  # fmt: skip

_MIN_YEAR: Final = 1900
_MAX_YEAR: Final = 2100

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_NUMERIC = re.compile(r"^(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})$")
_MONTH_FIRST = re.compile(
    r"^([A-Za-z]{3,9})\.?[\s-]+(\d{1,2})(?:st|nd|rd|th)?,?[\s-]+(\d{4})$", re.IGNORECASE
)
_DAY_FIRST = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)?\.?[\s-]+([A-Za-z]{3,9})\.?,?[\s-]+(\d{4})$", re.IGNORECASE
)


def _is_real_date(year: int, month: int, day: int) -> bool:
    """Whether the triple exists in the calendar, rejecting 31 April and friends."""
    if not (_MIN_YEAR <= year <= _MAX_YEAR):
        return False
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _iso(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_calendar_date(raw: str) -> DateParseResult:
    """Parse a date only when the reading is unambiguous.

    Returns `AMBIGUOUS` with both readings when a numeric date could be either
    day-first or month-first, so the decision reaches a human rather than being
    settled by assuming a locale.
    """
    text = trim_surrounding(raw)
    if not text:
        return DateParseResult(DateStatus.EMPTY)

    if match := _ISO.match(text):
        year, month, day = (int(part) for part in match.groups())
        if _is_real_date(year, month, day):
            return DateParseResult(DateStatus.PARSED, _iso(year, month, day), "ISO-8601")
        return DateParseResult(DateStatus.INVALID, reason=f"{text} is not a real calendar date")

    for pattern, order in ((_MONTH_FIRST, "month_first"), (_DAY_FIRST, "day_first")):
        if match := pattern.match(text):
            if order == "month_first":
                month_word, day_text, year_text = match.groups()
            else:
                day_text, month_word, year_text = match.groups()
            month = _MONTH_NAMES.get(month_word.lower(), 0)
            if not month:
                return DateParseResult(
                    DateStatus.INVALID, reason=f'unrecognised month "{month_word}"'
                )
            day, year = int(day_text), int(year_text)
            if _is_real_date(year, month, day):
                fmt = "MMMM D YYYY" if order == "month_first" else "D MMMM YYYY"
                return DateParseResult(DateStatus.PARSED, _iso(year, month, day), fmt)
            return DateParseResult(DateStatus.INVALID, reason=f"{text} is not a real calendar date")

    if match := _NUMERIC.match(text):
        first, second, third = match.groups()

        # A four-digit leading group can only be a year.
        if len(first) == 4:
            year, month, day = int(first), int(second), int(third)
            if _is_real_date(year, month, day):
                return DateParseResult(DateStatus.PARSED, _iso(year, month, day), "YYYY/MM/DD")
            return DateParseResult(DateStatus.INVALID, reason=f"{text} is not a real calendar date")

        if len(third) != 4:
            return DateParseResult(
                DateStatus.INVALID,
                reason=f"{text} has no four-digit year, so the century would be a guess",
            )

        year = int(third)
        a, b = int(first), int(second)
        day_first_valid = _is_real_date(year, b, a)
        month_first_valid = _is_real_date(year, a, b)

        if day_first_valid and month_first_valid:
            if a == b:
                # e.g. 05/05/2026 reads the same either way.
                return DateParseResult(DateStatus.PARSED, _iso(year, a, b), "identical either way")
            return DateParseResult(
                DateStatus.AMBIGUOUS,
                interpretations=(
                    DateInterpretation(_iso(year, b, a), "DD/MM/YYYY"),
                    DateInterpretation(_iso(year, a, b), "MM/DD/YYYY"),
                ),
            )
        if day_first_valid:
            return DateParseResult(DateStatus.PARSED, _iso(year, b, a), "DD/MM/YYYY")
        if month_first_valid:
            return DateParseResult(DateStatus.PARSED, _iso(year, a, b), "MM/DD/YYYY")
        return DateParseResult(DateStatus.INVALID, reason=f"{text} is not a real calendar date")

    return DateParseResult(DateStatus.INVALID, reason=f'"{text}" is not a recognised date format')


# ---------------------------------------------------------------------------
# Value shapes
# ---------------------------------------------------------------------------

_EMAIL_SHAPE = re.compile(r"^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$")
_IDENTIFIER_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_PERSON_NAME_SHAPE = re.compile(r"^[^\W\d_][^\d_]*(\s+[^\d_]+)+$", re.UNICODE)
_ENUM_SHAPE = re.compile(r"^[^\W\d_][\w\s-]{0,40}$", re.UNICODE)

#: Fraction of values that must match a shape before it is reported.
_SHAPE_THRESHOLD: Final = 0.8


def detect_value_kinds(values: list[str] | tuple[str, ...]) -> list[ValueKind]:
    """Infer which semantic kinds a column's values plausibly hold.

    Used as independent mapping evidence: a column of email addresses is not a
    credible start date, whatever its header claims.
    """
    present = [trimmed for value in values if (trimmed := trim_surrounding(value))]
    if not present:
        return []

    total = len(present)

    def ratio(predicate: object) -> float:
        assert callable(predicate)
        return sum(1 for value in present if predicate(value)) / total

    kinds: list[ValueKind] = []

    if ratio(lambda v: bool(_EMAIL_SHAPE.match(v))) >= _SHAPE_THRESHOLD:
        kinds.append(ValueKind.EMAIL)

    parsed_ratio = ratio(lambda v: parse_calendar_date(v).status is DateStatus.PARSED)
    date_like_ratio = ratio(
        lambda v: parse_calendar_date(v).status in {DateStatus.PARSED, DateStatus.AMBIGUOUS}
    )
    # Ambiguous values are still date-shaped; the mapping policy needs to know.
    if parsed_ratio >= _SHAPE_THRESHOLD or date_like_ratio >= _SHAPE_THRESHOLD:
        kinds.append(ValueKind.DATE)

    if ratio(lambda v: bool(_PERSON_NAME_SHAPE.match(v))) >= _SHAPE_THRESHOLD:
        kinds.append(ValueKind.PERSON_NAME)

    if (
        ValueKind.EMAIL not in kinds
        and ValueKind.DATE not in kinds
        and ratio(lambda v: bool(_IDENTIFIER_SHAPE.match(v)) and " " not in v) >= _SHAPE_THRESHOLD
    ):
        kinds.append(ValueKind.IDENTIFIER)

    if (
        ValueKind.DATE not in kinds
        and ratio(lambda v: bool(_ENUM_SHAPE.match(v))) >= _SHAPE_THRESHOLD
    ):
        distinct = len({value.lower() for value in present})
        if distinct <= max(8, int(total * 0.2)):
            kinds.append(ValueKind.ENUM)

    kinds.append(ValueKind.TEXT)
    return kinds
