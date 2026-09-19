"""A target schema handed over as a JSON or YAML spec.

The assignment describes the target as "a simple JSON/YAML spec you define or we
provide", so a spec file is a first-class way in — not a convenience on top of the
builder. These cases cover the three dialects a consultant actually arrives with,
and pin the two things that matter most: a spec is never executed, and what had to
be guessed is reported rather than presented as fact.
"""

from __future__ import annotations

import pytest

from schemabridge.domain.schema import ValueKind
from schemabridge.domain.spec import (
    MAX_SPEC_BYTES,
    SpecError,
    parse_spec,
    to_spec,
    to_yaml,
)
from schemabridge.domain.target import BUILTIN_SCHEMA

# A real API's published contract, which is the common case.
JSON_SCHEMA = """
{
  "title": "Customer",
  "description": "What the CRM expects.",
  "type": "object",
  "required": ["customerId", "primaryEmail"],
  "properties": {
    "customerId": {"type": "string", "title": "Customer ID", "maxLength": 32},
    "primaryEmail": {"type": "string", "format": "email"},
    "signedUp": {"type": "string", "format": "date"},
    "closedOn": {"type": ["string", "null"], "format": "date"},
    "plan": {"type": "string", "enum": ["free", "pro", "enterprise", null]},
    "notes": {"type": "string", "description": "Anything else."}
  }
}
"""

# What someone writes when asked for "a simple YAML spec".
YAML_FIELDS = """
name: Vendor
description: Suppliers we pay.
fields:
  - name: vendorRef
    label: Vendor reference
    kind: identifier
    required: true
    is_identity: true
  - name: contactEmail
    kind: email
    required: true
    is_unique: true
  - name: onboardedOn
    kind: date
  - name: category
    kind: enum
    enum_values: [goods, services]
    value_aliases:
      product: goods
      consulting: services
"""

BARE_MAP = """
name: Asset
assetTag: identifier
owner: name
purchasedOn: date
location: text
"""


class TestJsonSchemaDialect:
    def test_properties_become_fields_in_order(self) -> None:
        """Declaration order is kept: it decides the table's column order."""
        imported = parse_spec(JSON_SCHEMA)
        assert [f.name for f in imported.schema.fields] == [
            "customerId",
            "primaryEmail",
            "signedUp",
            "closedOn",
            "plan",
            "notes",
        ]
        assert imported.schema.name == "Customer"
        assert imported.schema.description == "What the CRM expects."

    def test_the_required_list_is_honoured(self) -> None:
        imported = parse_spec(JSON_SCHEMA)
        assert imported.schema.required_names == frozenset({"customerId", "primaryEmail"})

    def test_format_beats_type_when_pinning_a_kind(self) -> None:
        """`{"type": "string", "format": "email"}` is an email, not free text."""
        by_name = parse_spec(JSON_SCHEMA).schema.by_name
        assert by_name["primaryEmail"].kind is ValueKind.EMAIL
        assert by_name["signedUp"].kind is ValueKind.DATE
        assert by_name["notes"].kind is ValueKind.TEXT

    def test_an_enum_wins_over_the_type_word(self) -> None:
        plan = parse_spec(JSON_SCHEMA).schema.by_name["plan"]
        assert plan.kind is ValueKind.ENUM
        # The null that marks it optional is not a permitted value.
        assert plan.enum_values == ("free", "pro", "enterprise")

    def test_a_nullable_type_keeps_its_meaning(self) -> None:
        """["string", "null"] is a string that may be absent, not a union."""
        assert parse_spec(JSON_SCHEMA).schema.by_name["closedOn"].kind is ValueKind.DATE

    def test_a_title_becomes_the_label(self) -> None:
        assert parse_spec(JSON_SCHEMA).schema.by_name["customerId"].label == "Customer ID"

    def test_a_missing_title_gets_a_readable_label(self) -> None:
        """ "primaryEmail" reads as "Primary Email", not "Primaryemail"."""
        assert parse_spec(JSON_SCHEMA).schema.by_name["primaryEmail"].label == "Primary Email"


class TestOurOwnDialect:
    def test_everything_json_schema_cannot_say_survives(self) -> None:
        schema = parse_spec(YAML_FIELDS).schema
        assert schema.identity_field == "vendorRef"
        assert schema.unique_fields == ("contactEmail",)
        category = schema.by_name["category"]
        assert category.enum_values == ("goods", "services")
        assert category.value_aliases == {"product": "goods", "consulting": "services"}

    def test_a_declared_identity_is_not_second_guessed(self) -> None:
        imported = parse_spec(YAML_FIELDS)
        assert not any("identifies a record" in note for note in imported.assumptions)


class TestBareMapDialect:
    def test_a_field_to_type_map_is_accepted(self) -> None:
        """Not a standard anything, but it is what "a simple spec" means to people."""
        schema = parse_spec(BARE_MAP).schema
        assert [f.name for f in schema.fields] == [
            "assetTag",
            "owner",
            "purchasedOn",
            "location",
        ]
        assert schema.by_name["assetTag"].kind is ValueKind.IDENTIFIER
        assert schema.by_name["owner"].kind is ValueKind.PERSON_NAME
        assert schema.by_name["purchasedOn"].kind is ValueKind.DATE

    def test_the_name_key_is_not_read_as_a_field(self) -> None:
        assert parse_spec(BARE_MAP).schema.name == "Asset"


class TestKindFromTheFieldName:
    """A published JSON Schema usually pins nothing beyond `"type": "string"`.

    Without reading the name, every field in a real contract would import as free
    text — losing date normalisation, email checking, and the identifier that makes
    cross-file merging possible.
    """

    SPEC = """
    {"required": ["customerId"],
     "properties": {
       "customerId": {"type": "string"},
       "primaryEmail": {"type": "string"},
       "signedUpOn": {"type": "string"},
       "fullName": {"type": "string"},
       "notes": {"type": "string"},
       "candidate": {"type": "string"},
       "idVerified": {"type": "string"}
     }}
    """

    def test_a_bare_string_takes_its_kind_from_the_name(self) -> None:
        by_name = parse_spec(self.SPEC).schema.by_name
        assert by_name["customerId"].kind is ValueKind.IDENTIFIER
        assert by_name["primaryEmail"].kind is ValueKind.EMAIL
        assert by_name["signedUpOn"].kind is ValueKind.DATE
        assert by_name["fullName"].kind is ValueKind.PERSON_NAME

    def test_only_the_head_noun_counts(self) -> None:
        """ "candidate" ends in "date" and "idVerified" begins with "id"."""
        by_name = parse_spec(self.SPEC).schema.by_name
        assert by_name["candidate"].kind is ValueKind.TEXT
        assert by_name["idVerified"].kind is ValueKind.TEXT

    def test_a_name_with_no_signal_stays_text(self) -> None:
        assert parse_spec(self.SPEC).schema.by_name["notes"].kind is ValueKind.TEXT

    def test_a_stated_format_still_wins(self) -> None:
        """The spec's own word beats a guess from the name."""
        imported = parse_spec(
            '{"properties": {"startedOn": {"type": "string", "format": "email"}}}'
        )
        assert imported.schema.by_name["startedOn"].kind is ValueKind.EMAIL

    def test_a_stated_kind_still_wins(self) -> None:
        imported = parse_spec("fields:\n  - name: customerId\n    kind: text\n")
        assert imported.schema.by_name["customerId"].kind is ValueKind.TEXT


class TestWhatIsGuessedIsReported:
    def test_an_obvious_identifier_is_suggested_and_declared_as_a_guess(self) -> None:
        """JSON Schema cannot say which field identifies a record.

        Without this every import would merge nothing, so a two-file migration
        would produce duplicate records. The guess is stated, not hidden.
        """
        imported = parse_spec(JSON_SCHEMA)
        assert imported.schema.identity_field == "customerId"
        assert any("identifies a record" in note for note in imported.assumptions)

    def test_an_optional_identifier_is_not_promoted(self) -> None:
        """Guessing from an optional field risks merging records that are not one."""
        imported = parse_spec(
            '{"properties": {"maybeId": {"type": "string", "format": ""}}, "required": []}'
        )
        assert imported.schema.identity_field is None
        assert any("never be merged" in note for note in imported.assumptions)

    def test_a_required_email_is_flagged_unique(self) -> None:
        imported = parse_spec(JSON_SCHEMA)
        assert "primaryEmail" in imported.schema.unique_fields
        assert any("sharing" in note for note in imported.assumptions)

    def test_a_spec_marking_nothing_required_says_so(self) -> None:
        imported = parse_spec('{"properties": {"note": {"type": "string"}}}')
        assert any("required" in note for note in imported.assumptions)


class TestSafety:
    def test_yaml_is_never_executed(self) -> None:
        """A spec arrives in a request body, so `yaml.load` would be RCE."""
        dangerous = "!!python/object/apply:os.system ['echo pwned']"
        with pytest.raises(SpecError):
            parse_spec(dangerous)

    def test_a_python_tag_inside_a_field_is_refused(self) -> None:
        with pytest.raises(SpecError):
            parse_spec(
                "name: X\nfields:\n  - name: a\n    label: !!python/object/apply:os.system ['x']\n"
            )

    def test_an_oversized_spec_is_refused_before_parsing(self) -> None:
        with pytest.raises(SpecError, match="larger than"):
            parse_spec("x" * (MAX_SPEC_BYTES + 1))

    def test_too_many_fields_is_refused(self) -> None:
        fields = "\n".join(f"  f{index}: text" for index in range(60))
        with pytest.raises(SpecError, match="at most"):
            parse_spec(f"name: Big\nproperties:\n{fields}\n")


class TestUnreadableSpecs:
    def test_an_empty_file_says_so(self) -> None:
        with pytest.raises(SpecError, match="empty"):
            parse_spec("   \n  ")

    def test_malformed_yaml_names_the_line(self) -> None:
        with pytest.raises(SpecError, match="line"):
            parse_spec("name: X\nfields:\n  - name: a\n   bad indent: 1\n")

    def test_a_list_is_not_a_schema(self) -> None:
        with pytest.raises(SpecError, match="object"):
            parse_spec("[1, 2, 3]")

    def test_a_document_with_no_fields_explains_what_was_expected(self) -> None:
        with pytest.raises(SpecError, match="properties"):
            parse_spec('{"title": "Empty", "type": "object"}')

    def test_unusable_field_names_are_named_not_dropped_silently(self) -> None:
        """A missing column is worse than a refused import, so say which went."""
        imported = parse_spec(
            '{"properties": {"good": {"type": "string"}, "2bad": {"type": "string"}}}'
        )
        assert [f.name for f in imported.schema.fields] == ["good"]
        assert any("2bad" in note for note in imported.assumptions)

    def test_a_spec_where_nothing_is_usable_is_refused(self) -> None:
        with pytest.raises(SpecError, match="usable names"):
            parse_spec('{"properties": {"1": {"type": "string"}, "2": {"type": "string"}}}')


class TestRoundTrip:
    def test_the_builtin_template_survives_a_round_trip(self) -> None:
        """Export then import must not quietly lose a flag or a vocabulary."""
        written = to_yaml(BUILTIN_SCHEMA)
        restored = parse_spec(written).schema

        assert [f.name for f in restored.fields] == [f.name for f in BUILTIN_SCHEMA.fields]
        assert restored.required_names == BUILTIN_SCHEMA.required_names
        assert restored.identity_field == BUILTIN_SCHEMA.identity_field
        assert restored.unique_fields == BUILTIN_SCHEMA.unique_fields
        for original in BUILTIN_SCHEMA.fields:
            copy = restored.by_name[original.name]
            assert copy.kind is original.kind
            assert copy.label == original.label
            assert copy.enum_values == original.enum_values
            assert copy.value_aliases == original.value_aliases
            assert copy.not_before == original.not_before

    def test_a_round_trip_preserves_matching_behaviour(self) -> None:
        """The point of keeping the curated aliases: the same headers still match."""
        restored = parse_spec(to_yaml(BUILTIN_SCHEMA)).schema
        for header in ("doj", "emp_nm", "emp_type", "empid"):
            from schemabridge.domain.schema import normalize_header

            assert restored.fields_for_header(normalize_header(header)) == (
                BUILTIN_SCHEMA.fields_for_header(normalize_header(header))
            )

    def test_derived_spellings_are_not_written_out(self) -> None:
        """Freezing them would stop a later improvement reaching an imported schema."""
        document = to_spec(BUILTIN_SCHEMA)
        for entry in document["fields"]:
            assert "spellings" not in entry
