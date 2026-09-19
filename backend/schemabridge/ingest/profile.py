"""Column profiling.

A profile is what the mapping policy reasons about, and — for columns no alias
table recognises — what the model is shown. It is deliberately a summary: the
full dataset never leaves this function, and samples are capped and truncated.

`total_count` counts every row the column spans, including blanks, and
`non_empty_count` only those carrying a value. The difference is the signal: a
column filled 3 times in 200 rows is almost certainly not the required field it
is named after, and collapsing the two counts would hide that.
"""

from __future__ import annotations

import pandas as pd

from schemabridge.domain.models import ColumnProfile, SourceFile, SourceRow
from schemabridge.domain.normalize import detect_value_kinds, trim_surrounding
from schemabridge.ingest.limits import INGEST_LIMITS

_SAMPLE_MAX_LENGTH = 120


def profile_columns(
    source_file: SourceFile, rows: tuple[SourceRow, ...]
) -> tuple[ColumnProfile, ...]:
    """Summarise every column in a file."""
    frame = pd.DataFrame(
        [row.values for row in rows],
        columns=[column.id for column in source_file.columns],
        dtype="string",
    )

    profiles: list[ColumnProfile] = []
    for column in source_file.columns:
        series = frame[column.id] if column.id in frame.columns else pd.Series(dtype="string")
        present = [
            trimmed
            for value in series.tolist()
            if isinstance(value, str) and (trimmed := trim_surrounding(value))
        ]
        distinct = list(dict.fromkeys(present))  # preserves first-seen order
        # Every row the column spans, blanks included. Counting only the values
        # present would report a half-empty column as completely filled.
        total = len(series)

        profiles.append(
            ColumnProfile(
                column_id=column.id,
                header=column.header,
                file_name=source_file.name,
                total_count=total,
                non_empty_count=len(present),
                distinct_count=len(distinct),
                # Over the values actually present: a column with two distinct
                # values in two filled rows is fully unique in what it holds,
                # which is what type detection needs to know.
                unique_ratio=(len(distinct) / len(present)) if present else 0.0,
                detected_kinds=tuple(detect_value_kinds(present)),
                samples=tuple(
                    value
                    if len(value) <= _SAMPLE_MAX_LENGTH
                    else f"{value[: _SAMPLE_MAX_LENGTH - 3]}..."
                    for value in distinct[: INGEST_LIMITS.max_samples_per_column]
                ),
            )
        )
    return tuple(profiles)
