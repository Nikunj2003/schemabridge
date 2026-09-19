"""Value handling must never guess. These cases are the contract."""

from __future__ import annotations

import pytest

from schemabridge.domain.normalize import (
    DateStatus,
    detect_value_kinds,
    normalize_header,
    parse_calendar_date,
)
from schemabridge.domain.target import ValueKind


class TestNormalizeHeader:
    @pytest.mark.parametrize(
        "raw",
        ["Employee ID", "employee_id", "  Employee-ID  ", "EMPLOYEE.ID", "employee id"],
    )
    def test_spellings_reduce_to_one_key(self, raw: str) -> None:
        assert normalize_header(raw) == "employeeid"

    def test_collapses_internal_whitespace(self) -> None:
        assert normalize_header("Date   of  Joining") == "dateofjoining"

    def test_strips_byte_order_mark(self) -> None:
        assert normalize_header("﻿Employee ID") == "employeeid"

    def test_blank_header_is_empty(self) -> None:
        assert normalize_header("   ") == ""


class TestParseCalendarDate:
    def test_accepts_iso(self) -> None:
        result = parse_calendar_date("2026-03-04")
        assert result.status is DateStatus.PARSED
        assert result.value == "2026-03-04"

    @pytest.mark.parametrize(
        "raw",
        ["14 March 2026", "March 14, 2026", "14-Mar-2026", "Mar 14 2026"],
    )
    def test_accepts_month_names_in_either_order(self, raw: str) -> None:
        result = parse_calendar_date(raw)
        assert result.status is DateStatus.PARSED
        assert result.value == "2026-03-14"

    def test_resolves_numeric_when_only_one_ordering_is_real(self) -> None:
        # 25 cannot be a month, so this is unambiguously 25 December.
        result = parse_calendar_date("25/12/2026")
        assert result.status is DateStatus.PARSED
        assert result.value == "2026-12-25"

    def test_refuses_to_guess_when_both_orderings_are_valid(self) -> None:
        result = parse_calendar_date("03/04/2026")
        assert result.status is DateStatus.AMBIGUOUS
        assert [i.value for i in result.interpretations] == ["2026-04-03", "2026-03-04"]

    def test_identical_either_way_is_not_ambiguous(self) -> None:
        result = parse_calendar_date("05/05/2026")
        assert result.status is DateStatus.PARSED
        assert result.value == "2026-05-05"

    @pytest.mark.parametrize("raw", ["2026-02-30", "2025-02-29", "2026-13-01", "2026-04-31"])
    def test_rejects_dates_that_do_not_exist(self, raw: str) -> None:
        assert parse_calendar_date(raw).status is DateStatus.INVALID

    def test_accepts_a_real_leap_day(self) -> None:
        result = parse_calendar_date("2024-02-29")
        assert result.status is DateStatus.PARSED
        assert result.value == "2024-02-29"

    def test_blank_is_empty_not_invalid(self) -> None:
        assert parse_calendar_date("   ").status is DateStatus.EMPTY

    @pytest.mark.parametrize("raw", ["next tuesday", "2026", "sometime in March", "tomorrow"])
    def test_does_not_fall_back_to_loose_parsing(self, raw: str) -> None:
        # A permissive parser would happily invent a date here. That is exactly
        # the failure this function exists to prevent.
        assert parse_calendar_date(raw).status is DateStatus.INVALID

    def test_rejects_two_digit_year(self) -> None:
        # The century would be a guess.
        assert parse_calendar_date("03/04/26").status is DateStatus.INVALID

    def test_accepts_year_first_numeric(self) -> None:
        result = parse_calendar_date("2026/03/14")
        assert result.status is DateStatus.PARSED
        assert result.value == "2026-03-14"


class TestDetectValueKinds:
    def test_identifies_emails(self) -> None:
        assert ValueKind.EMAIL in detect_value_kinds(["a@b.com", "c.d@e.co.uk"])

    def test_identifies_dates(self) -> None:
        assert ValueKind.DATE in detect_value_kinds(["2026-01-01", "2026-06-15"])

    def test_identifies_identifiers(self) -> None:
        assert ValueKind.IDENTIFIER in detect_value_kinds(["E-1001", "E-1002", "E-1003"])

    def test_identifies_person_names(self) -> None:
        assert ValueKind.PERSON_NAME in detect_value_kinds(["Priya Sharma", "John Smith"])

    def test_ignores_blanks_when_deciding(self) -> None:
        assert ValueKind.DATE in detect_value_kinds(["", "  ", "2026-01-01"])

    def test_nothing_to_judge_returns_empty(self) -> None:
        assert detect_value_kinds(["", "   "]) == []

    def test_ambiguous_dates_still_count_as_date_shaped(self) -> None:
        # The mapping policy needs to know these are dates even though no single
        # reading is safe.
        assert ValueKind.DATE in detect_value_kinds(["03/04/2026", "05/06/2026"])
