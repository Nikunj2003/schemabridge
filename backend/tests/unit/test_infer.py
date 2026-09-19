"""A detected schema is a usable draft, and honest about being one.

What inference must get right is not "the correct schema" — it cannot know that —
but that everything it guesses is safe to have guessed wrong. So these cases check
the omissions as carefully as the inferences.
"""

from __future__ import annotations

from pathlib import Path

from schemabridge.domain.infer import infer_schema
from schemabridge.domain.mapping import decide_mappings
from schemabridge.domain.models import ColumnProfile, MappingOutcome, SourceColumn
from schemabridge.domain.schema import ValueKind
from schemabridge.ingest.csv_source import parse_csv
from schemabridge.ingest.profile import profile_columns

SAMPLES = Path(__file__).resolve().parents[2] / "fixtures" / "samples"


def load(
    name: str, file_id: str = "f1"
) -> tuple[tuple[SourceColumn, ...], tuple[ColumnProfile, ...]]:
    parsed = parse_csv(file_id, name, (SAMPLES / name).read_text(encoding="utf-8"))
    assert parsed.ok, parsed.error
    return parsed.file.columns, profile_columns(parsed.file, parsed.rows)


class TestNamesAndLabels:
    def test_headers_become_camel_case_field_names(self) -> None:
        columns, profiles = load("employees-hr-export.csv")
        schema = infer_schema(columns, profiles)
        names = [field.name for field in schema.fields]
        assert "employeeNumber" in names
        assert "fullName" in names
        assert "joiningDate" in names

    def test_labels_read_as_a_person_wrote_them(self) -> None:
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        labels = {field.name: field.label for field in schema.fields}
        # camelCase split back apart rather than shown as "Workemail".
        assert labels["workEmail"] == "Work Email"

    def test_a_terse_export_still_produces_valid_names(self) -> None:
        columns, profiles = load("employees-legacy.csv")
        schema = infer_schema(columns, profiles)
        assert [f.name for f in schema.fields] == [
            "empId",
            "empNm",
            "email",
            "doj",
            "dept",
            "empType",
        ]


class TestNonAsciiHeaders:
    """Folding a header to ASCII must not cut the word in half."""

    def test_accented_letters_keep_their_base_form(self) -> None:
        parsed = parse_csv("f1", "a.csv", "naïve,Zoë Ref\nA,B\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        # Not "naVe" and "zoRef", which is what splitting on the accent gives.
        assert [field.name for field in schema.fields] == ["naive", "zoeRef"]

    def test_a_letter_with_no_combining_mark_still_expands(self) -> None:
        """ "ß" has no mark to strip, so it needs casefolding to reach "ss"."""
        parsed = parse_csv("f1", "a.csv", "Größe\nA\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert schema.fields[0].name == "grosse"

    def test_camel_case_survives_the_folding(self) -> None:
        """Casefolding the whole header would flatten the word boundary."""
        parsed = parse_csv("f1", "a.csv", "workEmail\na@b.com\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert schema.fields[0].name == "workEmail"
        assert schema.fields[0].label == "Work Email"

    def test_a_label_keeps_what_the_file_said(self) -> None:
        """The label is read by a person; only the name has to be ASCII."""
        parsed = parse_csv("f1", "a.csv", "Ünité Coût\n12\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert schema.fields[0].name == "uniteCout"
        assert schema.fields[0].label == "Ünité Coût"

    def test_a_header_with_no_ascii_equivalent_still_yields_a_field(self) -> None:
        """A placeholder name, rather than a crash or a dropped column.

        The header has no ASCII form at all, so there is nothing to build a name
        from. The field still exists and the label still says what the file said,
        so the person can rename it in the builder.
        """
        parsed = parse_csv("f1", "a.csv", "日本語\nA\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert len(schema.fields) == 1
        assert schema.fields[0].name.startswith("field")
        # Kept, not dropped: the column holds data whatever its header looks like.
        # Nothing is lost: the original is still what the builder shows.
        assert schema.fields[0].label == "日本語"


class TestKinds:
    def test_value_kinds_come_from_the_values(self) -> None:
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        kinds = {field.name: field.kind for field in schema.fields}
        assert kinds["workEmail"] is ValueKind.EMAIL
        assert kinds["startDate"] is ValueKind.DATE

    def test_an_enum_is_never_inferred(self) -> None:
        """A closed vocabulary guessed wrong rejects every future value."""
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        assert all(field.kind is not ValueKind.ENUM for field in schema.fields)


class TestWhatIsDeliberatelyNotInferred:
    def test_nothing_is_marked_required(self) -> None:
        """A column full in this file may be optional in the destination."""
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        assert schema.required_names == frozenset()

    def test_no_identity_field_is_guessed(self) -> None:
        """An email column is distinct too; guessing splits or merges records."""
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        assert schema.identity_field is None

    def test_nothing_is_marked_unique(self) -> None:
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        assert schema.unique_fields == ()

    def test_it_says_it_needs_reviewing(self) -> None:
        columns, profiles = load("employees-clean.csv")
        schema = infer_schema(columns, profiles)
        assert "Review" in schema.description


class TestMultiFileAndEdgeCases:
    def test_a_header_shared_across_files_becomes_one_field(self) -> None:
        """Two files carrying "Employee ID" describe one field, not two."""
        legacy_columns, legacy_profiles = load("employees-legacy.csv", "legacy")
        hr_columns, hr_profiles = load("employees-hr-export.csv", "hr")
        schema = infer_schema([*legacy_columns, *hr_columns], [*legacy_profiles, *hr_profiles])
        names = [field.name for field in schema.fields]
        assert len(names) == len(set(names))
        assert names.count("email") == 1

    def test_row_number_columns_are_left_out(self) -> None:
        parsed = parse_csv("f1", "a.csv", "S.No,Name\n1,Asha\n2,Ravi\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert [field.name for field in schema.fields] == ["name"]

    def test_headers_meaning_the_same_thing_collapse_to_one_field(self) -> None:
        """ "emp id" and "emp_id" differ only in punctuation, so they are one field."""
        parsed = parse_csv("f1", "a.csv", "emp id,emp_id\nA,B\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert [field.name for field in schema.fields] == ["empId"]

    def test_distinct_headers_reducing_to_one_name_are_numbered(self) -> None:
        """Numbered rather than dropped: neither column silently disappears.

        These two headers differ before normalisation but fold to the same field
        name, which is the only way a collision survives the dedup above.
        """
        parsed = parse_csv("f1", "a.csv", "Größe,Grosse\nA,B\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        assert [field.name for field in schema.fields] == ["grosse", "grosse2"]
        # Both labels keep what the file actually said.
        assert [field.label for field in schema.fields] == ["Größe", "Grosse"]

    def test_a_numeric_header_still_yields_a_valid_name(self) -> None:
        parsed = parse_csv("f1", "a.csv", "2026,Name\nx,Asha\n")
        assert parsed.ok
        schema = infer_schema(parsed.file.columns, profile_columns(parsed.file, parsed.rows))
        # A field name cannot begin with a digit, and the model enforces it.
        assert schema.fields[0].name == "field2026"


class TestADetectedSchemaActuallyWorks:
    def test_the_file_it_was_detected_from_maps_cleanly(self) -> None:
        """The point of detection: no escalations on the file that produced it.

        If a detected schema escalated its own source columns, it would be worse
        than useless — the reviewer would answer a question inference created.
        """
        columns, profiles = load("employees-legacy.csv")
        schema = infer_schema(columns, profiles)
        result = decide_mappings(columns, profiles, schema=schema)

        assert result.issues == ()
        assert result.unresolved == ()
        assert all(d.outcome is MappingOutcome.AUTO_MAPPED for d in result.decisions)
        assert len({d.target for d in result.decisions}) == len(result.decisions)
