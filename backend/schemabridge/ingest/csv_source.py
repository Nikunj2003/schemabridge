"""CSV parsing.

Every value stays a string. Coercing types here would turn the identifier
"000123" into the number 123, and a migration cannot un-lose a leading zero.
Duplicate headers keep their own identity by position, so a file carrying two
columns both named "date" does not silently lose one.
"""

from __future__ import annotations

import csv
import hashlib
import io

from schemabridge.domain.models import SourceColumn, SourceFile, SourceKind, SourceRow
from schemabridge.domain.normalize import normalize_header, trim_surrounding
from schemabridge.ingest.limits import INGEST_LIMITS
from schemabridge.ingest.result import ParseResult


def _columns(file_id: str, file_name: str, headers: list[str]) -> tuple[SourceColumn, ...]:
    return tuple(
        SourceColumn(
            id=f"{file_id}:c{index}",
            file_id=file_id,
            file_name=file_name,
            header=trim_surrounding(header),
            normalized_header=normalize_header(header),
            index=index,
        )
        for index, header in enumerate(headers)
    )


def parse_csv(file_id: str, file_name: str, content: str) -> ParseResult:
    """Parse CSV text into columns and rows, enforcing every limit."""
    warnings: list[str] = []

    try:
        reader = csv.reader(io.StringIO(content, newline=""))
        grid = [row for row in reader if any(trim_surrounding(cell) for cell in row)]
    except csv.Error as error:
        return ParseResult.failure(f"{file_name}: could not be parsed as CSV ({error}).")

    if not grid:
        return ParseResult.failure(f"{file_name}: the file is empty.")

    headers = [trim_surrounding(cell) for cell in grid[0]]
    data_rows = grid[1:]

    if not any(headers):
        return ParseResult.failure(f"{file_name}: the header row is empty.")
    if len(headers) > INGEST_LIMITS.max_columns:
        return ParseResult.failure(
            f"{file_name}: {len(headers)} columns exceeds the limit of {INGEST_LIMITS.max_columns}."
        )
    if not data_rows:
        return ParseResult.failure(f"{file_name}: the file has headers but no data rows.")
    if len(data_rows) > INGEST_LIMITS.max_rows_per_file:
        return ParseResult.failure(
            f"{file_name}: {len(data_rows)} rows exceeds the limit of "
            f"{INGEST_LIMITS.max_rows_per_file}."
        )

    columns = _columns(file_id, file_name, headers)
    rows: list[SourceRow] = []

    for index, cells in enumerate(data_rows):
        for position, cell in enumerate(cells):
            if len(cell) > INGEST_LIMITS.max_cell_length:
                header = headers[position] if position < len(headers) else position + 1
                return ParseResult.failure(
                    f'{file_name}: a cell in column "{header}" is too long '
                    f"(limit {INGEST_LIMITS.max_cell_length} characters)."
                )
        if len(cells) > len(headers):
            warnings.append(
                f"{file_name} row {index + 2} has more cells than headers; the extras were ignored."
            )

        values = {
            column.id: (cells[column.index] if column.index < len(cells) else "")
            for column in columns
        }
        # Row 1 is the header, so data starts at 2 — the number a person sees.
        rows.append(
            SourceRow(id=f"{file_id}:r{index + 2}", file_id=file_id, row=index + 2, values=values)
        )

    source_file = SourceFile(
        id=file_id,
        name=file_name,
        kind=SourceKind.CSV,
        sheet=None,
        byte_size=len(content.encode("utf-8")),
        checksum=hashlib.sha256(content.encode("utf-8")).hexdigest()[:32],
        columns=columns,
        row_count=len(rows),
    )
    return ParseResult.success(source_file, tuple(rows), tuple(warnings))
