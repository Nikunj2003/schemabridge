"""Shared parse result, so CSV and Excel report failures the same way."""

from __future__ import annotations

from dataclasses import dataclass, field

from schemabridge.domain.models import SourceFile, SourceRow


@dataclass(frozen=True, slots=True)
class ParseResult:
    ok: bool
    file: SourceFile = None  # type: ignore[assignment]
    rows: tuple[SourceRow, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)
    error: str = ""

    @classmethod
    def failure(cls, error: str) -> ParseResult:
        return cls(ok=False, error=error)

    @classmethod
    def success(
        cls,
        source_file: SourceFile,
        rows: tuple[SourceRow, ...],
        warnings: tuple[str, ...] = (),
    ) -> ParseResult:
        return cls(ok=True, file=source_file, rows=rows, warnings=warnings)
