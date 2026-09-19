"""Server-enforced ingestion limits.

These are deliberately small. The demo runs on free-tier capacity, and the
platform caps a request body at 4.5 MB, so the combined upload limit sits well
under that. `max_expanded_bytes` guards separately against a small compressed
workbook expanding into an enormous sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class IngestLimits:
    max_files: int = 3
    max_total_bytes: int = 2 * 1024 * 1024
    max_rows_per_file: int = 500
    max_total_rows: int = 1_000
    max_columns: int = 50
    max_cell_length: int = 2_000
    max_samples_per_column: int = 5
    max_expanded_bytes: int = 16 * 1024 * 1024
    max_sheets: int = 32
    #: Kept below MongoDB's 16 MB document ceiling, with room for audit growth.
    max_stored_run_bytes: int = 8 * 1024 * 1024


INGEST_LIMITS: Final = IngestLimits()
