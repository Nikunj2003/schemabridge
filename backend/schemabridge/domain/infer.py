"""Deriving a target schema from the uploaded files themselves.

The third way to get a schema, alongside picking a saved one and building one by
hand: when someone has a file and no contract, the file's own headers are a
reasonable first draft.

This is a *draft*, and the distinction matters. Inference reads headers and
detected value kinds, both of which can be wrong, so what comes back is something
to review in the builder rather than something to migrate against. Two things are
deliberately never inferred:

* **Required.** A column full in this file may be optional in the destination.
  Marking it required would block a later migration on a value that was never
  mandatory.
* **Identity.** A column with distinct values in one upload is not thereby an
  identifier — an email column is distinct too. Guessing wrong either merges two
  records or splits one, so the builder asks instead.

Uniqueness is likewise left off. What *is* inferred is the part that is safe to
get wrong and easy to see: field names, labels and value kinds.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from schemabridge.domain.models import ColumnProfile, SourceColumn
from schemabridge.domain.normalize import detect_value_kinds
from schemabridge.domain.schema import (
    MAX_FIELDS,
    TargetFieldSpec,
    TargetSchema,
    ValueKind,
    normalize_header,
)

#: Headers that are structural rather than data: row numbers and export
#: artefacts. Carrying them into the contract means delivering them.
#:
#: The empty string is deliberately absent. A header that normalises to nothing —
#: one written entirely in a script with no ASCII form, or made only of
#: punctuation — is still a column holding data, and dropping it would lose that
#: data silently. It becomes a numbered placeholder field instead, keeping its
#: original text as the label so the person can name it.
_SKIP = frozenset({"sno", "srno", "serialno", "index", "rowid", "row", "no", "sl", "slno"})


def _ascii_fold(text: str) -> str:
    """Non-ASCII letters reduced to their nearest ASCII form.

    Field names must be ASCII to be safe as JSON keys, and the naive approach —
    splitting the header on anything non-alphanumeric — cuts words in half:
    "Naïve" becomes "naVe" and "Größe" becomes "groE", neither of which the person
    who wrote the header would recognise as theirs.

    Decomposing and dropping combining marks turns "ï" into "i" rather than
    removing the letter. A character that survives that and is still non-ASCII is
    casefolded individually, which catches the expansions no decomposition
    handles: "ß" has no mark to strip but casefolds to "ss". Casefolding only
    those characters matters — doing it to the whole header would flatten
    "workEmail" to "workemail" and lose the word boundary the camelCase carries.

    Anything still outside ASCII has no sensible mapping, so it becomes a
    separator and `_field_name` works with what is left. The label keeps the
    original text regardless.
    """
    out: list[str] = []
    for character in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(character):
            continue
        if character.isascii():
            out.append(character)
            continue
        folded = unicodedata.normalize("NFKD", character.casefold())
        out.append("".join(c for c in folded if c.isascii() and not unicodedata.combining(c)))
    return "".join(out)


def _field_name(header: str, taken: set[str]) -> str:
    """A header turned into a valid, unique field name.

    camelCase because that is what a JSON destination conventionally expects, and
    because it matches the built-in template a user will see beside it.
    """
    words = [word for word in re.split(r"[^A-Za-z0-9]+", _ascii_fold(header)) if word]
    if not words:
        words = ["field"]
    # A leading digit cannot start a field name.
    if words[0][0].isdigit():
        words.insert(0, "field")

    head, *rest = words
    candidate = head[0].lower() + head[1:] + "".join(w[0].upper() + w[1:] for w in rest)
    candidate = re.sub(r"[^A-Za-z0-9_]", "", candidate)[:64] or "field"

    if candidate not in taken:
        return candidate
    # Two headers reducing to one name: number them rather than dropping either.
    for suffix in range(2, 100):
        numbered = f"{candidate}{suffix}"
        if numbered not in taken:
            return numbered
    return f"{candidate}{len(taken)}"


def _label(header: str) -> str:
    """The header as a person should read it, tidied but not reworded.

    Splits on separators and underscores only, keeping every letter as written —
    unlike `_field_name`, which must fold to ASCII. A label reading "Unite Cout"
    when the file said "Unité Coût" would look like a transcription error, and
    "Na ve" would look like a bug.
    """
    words = [word for word in re.split(r"[\s_\-./\\|]+", header.strip()) if word]
    if not words:
        return "Field"
    spaced = " ".join(words)
    # Split camelCase so "workEmail" reads as "Work Email" rather than "Workemail".
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", spaced)
    return spaced[0].upper() + spaced[1:]


def _kind(profile: ColumnProfile | None) -> ValueKind:
    """The value kind the column's own values suggest.

    An enum is deliberately never inferred: a column holding four distinct values
    might be a closed vocabulary or might be four of a thousand, and declaring an
    enum wrongly rejects every future value outside it. TEXT accepts everything
    and can be narrowed in the builder.
    """
    if profile is None:
        return ValueKind.TEXT
    kinds = profile.detected_kinds or tuple(detect_value_kinds(list(profile.samples)))
    if not kinds:
        return ValueKind.TEXT
    detected = kinds[0]
    return ValueKind.TEXT if detected is ValueKind.ENUM else detected


def infer_schema(
    columns: Sequence[SourceColumn],
    profiles: Sequence[ColumnProfile],
    *,
    name: str = "Detected schema",
) -> TargetSchema:
    """A first-draft contract matching the uploaded files.

    Columns sharing a header across files become one field, which is what makes
    the draft usable for a multi-file migration: two files both carrying
    "Employee ID" describe one field, not two.
    """
    by_id = {profile.column_id: profile for profile in profiles}

    fields: list[TargetFieldSpec] = []
    taken: set[str] = set()
    seen_headers: set[str] = set()

    for index, column in enumerate(columns):
        normalized = normalize_header(column.header)
        if normalized in _SKIP:
            continue
        # Deduplicate on the header, but only when there is a header to compare:
        # two columns that both normalise to nothing are not thereby the same
        # column, so they are kept apart by position.
        identity = normalized or f"\x00position:{index}"
        if identity in seen_headers:
            continue
        seen_headers.add(identity)

        field_name = _field_name(column.header, taken)
        taken.add(field_name)
        fields.append(
            TargetFieldSpec(
                name=field_name,
                # The header as written, even when the name had to be folded or
                # replaced — it is how the person recognises their own column.
                label=_label(column.header),
                kind=_kind(by_id.get(column.id)),
            )
        )
        if len(fields) >= MAX_FIELDS:
            break

    if not fields:
        # A schema needs at least one field, and an upload with no usable headers
        # is better served by an obvious placeholder than by an exception.
        fields.append(TargetFieldSpec(name="field1", label="Field 1"))

    return TargetSchema(
        schema_id="detected",
        name=name,
        description="Detected from the uploaded files. Review before relying on it.",
        fields=tuple(fields),
    )
