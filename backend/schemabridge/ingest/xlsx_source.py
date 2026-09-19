"""Excel parsing.

Two hazards shape the rules. A formula cell carries a *cached* result that may
be stale, or — if the workbook was generated programmatically and never opened
in a spreadsheet application — may not exist at all. Reading such a file with
cached values alone turns the formula into an empty string, which is silent data
loss. So the workbook is opened twice: once to see the formulas and reject them,
and once for the values. A workbook with more than one populated sheet is
refused rather than guessing which was meant, because quietly ignoring a sheet
hides data from the reviewer.

Dates are read as real datetimes by openpyxl, which applies the workbook's own
epoch. An arbitrary number is never assumed to be a date.
"""

from __future__ import annotations

import hashlib
import io
from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from schemabridge.domain.models import SourceColumn, SourceFile, SourceKind, SourceRow
from schemabridge.domain.normalize import normalize_header, trim_surrounding
from schemabridge.ingest.limits import INGEST_LIMITS
from schemabridge.ingest.result import ParseResult


class CellRejectedError(Exception):
    """A cell carries something this importer will not silently accept."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _cell_to_text(value: Any) -> str:
    """Render a cell as the string a person would see, or refuse it."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
        if text.startswith("="):
            raise CellRejectedError("contains a formula, whose cached result may be stale")
        if text.startswith("#") and text.rstrip("#").upper() in {
            "REF!",
            "VALUE!",
            "DIV/0!",
            "NAME?",
            "N/A",
            "NULL!",
            "NUM!",
        }:
            raise CellRejectedError(f"contains the spreadsheet error {text}")
        return text
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        # openpyxl has already applied the workbook's date epoch. Keep the
        # calendar date: the target contract stores dates without a time.
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float):
        return str(value)
    raise CellRejectedError("has a cell type this importer does not handle")


def _find_formula(sheet: Any) -> tuple[str, str] | None:
    """Locate the first formula cell, so the file can be refused by name."""
    for row in sheet.iter_rows():
        for cell in row:
            value = cell.value
            if isinstance(value, str) and value.startswith("="):
                formula = value if len(value) <= 40 else f"{value[:37]}..."
                return str(cell.coordinate), formula
            if cell.data_type == "f":
                return str(cell.coordinate), "(shared formula)"
    return None


def _populated_sheets(workbook: Any) -> list[Worksheet]:
    sheets: list[Worksheet] = []
    for sheet in workbook.worksheets:
        if sheet.sheet_state == "veryHidden":
            continue
        if (sheet.max_row or 0) > 1 and any(
            cell.value is not None for row in sheet.iter_rows(min_row=2) for cell in row
        ):
            sheets.append(sheet)
    return sheets


def parse_xlsx(file_id: str, file_name: str, data: bytes) -> ParseResult:
    """Parse an .xlsx workbook into columns and rows, enforcing every limit."""
    try:
        # Opened twice deliberately. `data_only=True` yields cached values but
        # hides formulas entirely; `data_only=False` exposes the formula text so
        # it can be rejected. Reading only the cached view would turn a formula
        # with no cached result into an empty cell without anyone noticing.
        workbook = load_workbook(io.BytesIO(data), read_only=False, data_only=True)
        formula_view = load_workbook(io.BytesIO(data), read_only=False, data_only=False)
    except Exception as error:  # openpyxl raises a variety of types
        return ParseResult.failure(
            f"{file_name}: could not be read as an .xlsx workbook ({error})."
        )

    try:
        if len(workbook.worksheets) > INGEST_LIMITS.max_sheets:
            return ParseResult.failure(f"{file_name}: too many worksheets.")

        populated = _populated_sheets(workbook)
        if not populated:
            return ParseResult.failure(f"{file_name}: no worksheet contains data rows.")
        if len(populated) > 1:
            names = ", ".join(f'"{sheet.title}"' for sheet in populated)
            return ParseResult.failure(
                f"{file_name}: {len(populated)} worksheets contain data ({names}). "
                f"Please upload one entity per file."
            )

        sheet = populated[0]

        if rejection := _find_formula(formula_view[sheet.title]):
            cell_ref, formula = rejection
            return ParseResult.failure(
                f"{file_name}: the cell at {cell_ref} contains the formula "
                f'"{formula}", whose result may be stale or absent. Please export '
                f"values rather than formulas."
            )

        width = sheet.max_column or 0
        height = sheet.max_row or 0

        if width > INGEST_LIMITS.max_columns:
            return ParseResult.failure(
                f"{file_name}: {width} columns exceeds the limit of {INGEST_LIMITS.max_columns}."
            )
        if height - 1 > INGEST_LIMITS.max_rows_per_file:
            return ParseResult.failure(
                f"{file_name}: {height - 1} rows exceeds the limit of "
                f"{INGEST_LIMITS.max_rows_per_file}."
            )

        headers: list[str] = []
        for position in range(1, width + 1):
            try:
                text = _cell_to_text(sheet.cell(row=1, column=position).value)
            except CellRejectedError as rejected:
                return ParseResult.failure(
                    f"{file_name}: the header in column {position} {rejected.reason}."
                )
            headers.append(trim_surrounding(text))

        if not any(headers):
            return ParseResult.failure(f"{file_name}: the header row is empty.")

        columns = tuple(
            SourceColumn(
                id=f"{file_id}:c{index}",
                file_id=file_id,
                file_name=file_name,
                header=header,
                normalized_header=normalize_header(header),
                index=index,
            )
            for index, header in enumerate(headers)
        )

        rows: list[SourceRow] = []
        expanded = 0

        for row_number in range(2, height + 1):
            values: dict[str, str] = {}
            has_content = False

            for column in columns:
                try:
                    text = _cell_to_text(sheet.cell(row=row_number, column=column.index + 1).value)
                except CellRejectedError as rejected:
                    return ParseResult.failure(
                        f"{file_name}: the cell at row {row_number}, column "
                        f'"{column.header}" {rejected.reason}. Please export values '
                        f"rather than formulas."
                    )
                if len(text) > INGEST_LIMITS.max_cell_length:
                    return ParseResult.failure(
                        f'{file_name}: a cell in column "{column.header}" is too long '
                        f"(limit {INGEST_LIMITS.max_cell_length} characters)."
                    )
                expanded += len(text)
                if expanded > INGEST_LIMITS.max_expanded_bytes:
                    return ParseResult.failure(
                        f"{file_name}: the sheet expands to more data than the limit allows."
                    )
                values[column.id] = text
                if trim_surrounding(text):
                    has_content = True

            if not has_content:
                continue  # Blank spacer row.
            rows.append(
                SourceRow(
                    id=f"{file_id}:r{row_number}",
                    file_id=file_id,
                    row=row_number,
                    values=values,
                )
            )

        if not rows:
            return ParseResult.failure(f"{file_name}: the worksheet has headers but no data rows.")

        source_file = SourceFile(
            id=file_id,
            name=file_name,
            kind=SourceKind.XLSX,
            sheet=sheet.title,
            byte_size=len(data),
            checksum=hashlib.sha256(data).hexdigest()[:32],
            columns=columns,
            row_count=len(rows),
        )
        return ParseResult.success(source_file, tuple(rows))
    finally:
        workbook.close()
        formula_view.close()
