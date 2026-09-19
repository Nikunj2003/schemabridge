"""The target contract, as data.

A migration maps onto whatever shape the client's destination expects, and that
differs per engagement. So a schema is a value the run carries, not a constant
compiled into the policy.

Three things follow from that, and each is load-bearing:

* **Value kinds stay a closed set.** A user picks from six semantic kinds, which
  is what lets cleanup, validation and type-compatibility keep working on a
  schema nobody wrote code for. A free-text type would mean no safe repairs at
  all.
* **Header spellings are derived, not demanded.** Nobody building a schema in a
  hurry will list that `doj` means a start date, so the spellings are generated
  from the field's own name and a small vocabulary of abbreviations. Matching is
  still exact-after-normalisation, so a derived spelling cannot match loosely.
* **The JSON Schema is generated from the fields.** Keeping a hand-written schema
  file beside a field list means two definitions that can disagree.
"""

from __future__ import annotations

import itertools
import re
from enum import StrEnum
from functools import cached_property
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ValueKind(StrEnum):
    """Semantic shape of a value.

    Closed on purpose. Every safe repair, type-compatibility check and validation
    rule keys off this, so a free-text type would mean a user-defined field got no
    cleanup and no checking at all. Six kinds cover the shapes that carry
    different *rules*, not merely different names.

    Defined here rather than beside the built-in template because the generic
    schema model is what needs it; the template is just one value of that model.
    """

    IDENTIFIER = "identifier"
    PERSON_NAME = "person_name"
    EMAIL = "email"
    DATE = "date"
    TEXT = "text"
    ENUM = "enum"


#: A field name has to survive being a JSON key, a CSV header and a Python dict
#: key, so it is deliberately narrow.
_NAME_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

MAX_FIELDS: Final = 40


class TargetFieldSpec(BaseModel):
    """One field in the target contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(description="The destination's own field name.")
    label: str = Field(description="How the field is named to a person.")
    description: str = ""
    required: bool = False
    kind: ValueKind = ValueKind.TEXT

    #: Marks the field that says which record is which. Cross-file merging keys
    #: on it, so without one every row is a separate record.
    is_identity: bool = False
    #: Two records sharing this value is worth a human's attention — the same
    #: address under two ids is either a duplicate or a mistake, and the schema
    #: alone cannot say which.
    is_unique: bool = False

    #: Extra header spellings, beyond those derived from the name. The built-in
    #: template curates these; a user schema normally leaves them empty.
    aliases: frozenset[str] = frozenset()
    #: Permitted values, for an ENUM field.
    enum_values: tuple[str, ...] = ()
    #: Accepted spellings for each permitted value, so "Permanent" and
    #: "full-time" can both canonicalise to the same member.
    value_aliases: dict[str, str] = Field(default_factory=dict)

    #: Names the field this one must not precede, for a date pair. JSON Schema
    #: cannot express it, so validation checks it separately.
    not_before: str | None = None

    #: Longest accepted value, when the destination is stricter than the kind's
    #: default. None means the default for the kind.
    max_length: int | None = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not _NAME_PATTERN.match(value):
            raise ValueError(
                "A field name must start with a letter and contain only letters, "
                "digits and underscores."
            )
        return value

    @model_validator(mode="after")
    def _check_enum(self) -> TargetFieldSpec:
        if self.kind is ValueKind.ENUM and not self.enum_values:
            raise ValueError(f"{self.name} is an enum field but lists no permitted values.")
        return self

    @cached_property
    def spellings(self) -> frozenset[str]:
        """Every header that unambiguously means this field."""
        return frozenset(
            derive_spellings(self.name, self.label)
            | {normalize_header(alias) for alias in self.aliases}
        ) - {""}


class TargetSchema(BaseModel):
    """A complete target contract.

    Snapshotted into a run rather than referenced by id: editing a schema must
    not silently change what a paused migration is being validated against.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_id: str
    name: str
    description: str = ""
    fields: tuple[TargetFieldSpec, ...]
    #: Bumped on every edit, so a run records which revision it used.
    version: int = 1
    #: True for the shipped template, which cannot be edited in place.
    builtin: bool = False

    @model_validator(mode="after")
    def _check_fields(self) -> TargetSchema:
        if not self.fields:
            raise ValueError("A target schema needs at least one field.")
        if len(self.fields) > MAX_FIELDS:
            raise ValueError(f"A target schema may not have more than {MAX_FIELDS} fields.")

        names = [field.name for field in self.fields]
        duplicated = {name for name in names if names.count(name) > 1}
        if duplicated:
            raise ValueError(f"Duplicate field name: {sorted(duplicated)[0]}.")

        identities = [field.name for field in self.fields if field.is_identity]
        if len(identities) > 1:
            raise ValueError(
                f"Only one field can identify a record; {', '.join(identities)} are all marked."
            )

        known = set(names)
        for field in self.fields:
            if field.not_before and field.not_before not in known:
                raise ValueError(
                    f"{field.name} is ordered against {field.not_before}, "
                    f"which this schema does not define."
                )
        return self

    # --- lookups -------------------------------------------------------

    @cached_property
    def by_name(self) -> dict[str, TargetFieldSpec]:
        return {field.name: field for field in self.fields}

    def field(self, name: str) -> TargetFieldSpec | None:
        return self.by_name.get(name)

    def has(self, name: str) -> bool:
        return name in self.by_name

    @cached_property
    def required_names(self) -> frozenset[str]:
        return frozenset(field.name for field in self.fields if field.required)

    @cached_property
    def identity_field(self) -> str | None:
        """The field that says which record is which, if the schema names one."""
        return next((field.name for field in self.fields if field.is_identity), None)

    @cached_property
    def naming_field(self) -> str | None:
        """The field that best names a record to a person.

        Not the same question as `identity_field`, which is about *merging* and is
        only ever set deliberately. This is about display, so a reasonable guess
        is fine and much better than the alternative: a detected schema declares
        no identity, and falling back to an internal `rec:row-3` shows a reviewer
        a handle they cannot find anywhere in their file.

        Preference order is how recognisable each kind is: a person's name, then
        the declared identity, then any identifier, then the first required
        field.
        """
        for kind in (ValueKind.PERSON_NAME,):
            for field in self.fields:
                if field.kind is kind:
                    return field.name
        if self.identity_field:
            return self.identity_field
        for field in self.fields:
            if field.kind is ValueKind.IDENTIFIER:
                return field.name
        for field in self.fields:
            if field.required:
                return field.name
        return None

    @cached_property
    def unique_fields(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if field.is_unique)

    @cached_property
    def spelling_index(self) -> dict[str, tuple[str, ...]]:
        """Normalised header to the field names that claim it.

        A header claimed by two fields is ambiguous by construction — which is
        how a bare "Date" column ends up asking whether it means the start or the
        end, without any hardcoded list of ambiguous headers.
        """
        index: dict[str, list[str]] = {}
        for field in self.fields:
            for spelling in field.spellings:
                index.setdefault(spelling, []).append(field.name)
        return {header: tuple(names) for header, names in index.items()}

    def fields_for_header(self, normalized_header: str) -> tuple[str, ...]:
        return self.spelling_index.get(normalized_header, ())

    # --- validation contract -------------------------------------------

    @cached_property
    def json_schema(self) -> dict[str, Any]:
        """The JSON Schema a record is validated against.

        Generated so it cannot drift from the field list.
        """
        properties: dict[str, Any] = {}
        for field in self.fields:
            properties[field.name] = _property_for(field)
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": self.name,
            "description": self.description,
            "type": "object",
            # Anything not named here is not part of the contract, so sending it
            # would be inventing data the destination never asked for.
            "additionalProperties": False,
            "required": sorted(self.required_names),
            "properties": properties,
        }


def _property_for(field: TargetFieldSpec) -> dict[str, Any]:
    """One field's JSON Schema, derived from its kind."""
    nullable = not field.required

    if field.kind is ValueKind.ENUM:
        values: list[Any] = list(field.enum_values)
        if nullable:
            values.append(None)
        return {
            "type": ["string", "null"] if nullable else "string",
            "title": field.label,
            "description": field.description,
            "enum": values,
        }

    base: dict[str, Any]
    if field.kind is ValueKind.EMAIL:
        base = {"type": "string", "format": "email", "maxLength": 254}
    elif field.kind is ValueKind.DATE:
        base = {"type": "string", "format": "date"}
    elif field.kind is ValueKind.IDENTIFIER:
        # An identifier is an opaque string, never a number: treating "000123" as
        # numeric would drop the leading zeros and change who it refers to.
        base = {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._/-]*$",
        }
    elif field.kind is ValueKind.PERSON_NAME:
        base = {"type": "string", "minLength": 1, "maxLength": 200}
    else:
        base = {"type": "string", "maxLength": 500}

    if nullable:
        base["type"] = [base["type"], "null"]
    if field.max_length is not None:
        base["maxLength"] = field.max_length
    base["title"] = field.label
    if field.description:
        base["description"] = field.description
    return base


# ---------------------------------------------------------------------------
# Header spellings
# ---------------------------------------------------------------------------

#: Abbreviations and synonyms seen in real exports, kept at the level of ordinary
#: vocabulary rather than tied to any one schema — so "emp" expands for an
#: employee schema and "dept" for any schema with a department field.
#:
#: Deliberately conservative. A wrong entry here silently migrates the wrong
#: column, which is far worse than escalating an unfamiliar header.
_VOCABULARY: Final[dict[str, tuple[str, ...]]] = {
    "employee": ("emp", "empl", "staff", "worker", "personnel", "associate"),
    "identifier": ("id", "no", "num", "number", "code", "ref"),
    "id": ("no", "num", "number", "code", "ref"),
    "name": ("nm", "nam"),
    "email": ("mail", "eml", "emailaddress", "mailid"),
    "phone": ("tel", "telephone", "mobile", "contact"),
    "date": ("dt", "on"),
    "department": ("dept", "div", "division", "team", "unit", "function"),
    "type": ("typ", "kind", "category", "cat"),
    "status": ("state", "stat"),
    "start": ("join", "joining", "joined", "hire", "hired", "commencement", "from"),
    "end": ("exit", "leaving", "left", "termination", "separation", "last", "to"),
    "work": ("office", "company", "business", "corporate", "official"),
    "full": ("complete", "legal", "display"),
    "employment": ("engagement", "contract", "job"),
    "first": ("fore", "given"),
    "last": ("sur", "family"),
    "amount": ("amt", "value", "total"),
    "address": ("addr", "location"),
    "city": ("town",),
    "country": ("nation",),
}


def normalize_header(header: str) -> str:
    """A header reduced to what it means, ignoring how it was typed."""
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _split_words(name: str, label: str) -> list[str]:
    """The words a field name is made of.

    Prefers the name (`startDate` → start, date) and falls back to the label for
    a single-word name, since "Employee ID" carries more than "id" does.
    """
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).lower().split()
    words = [word for chunk in words for word in re.split(r"[_\-]+", chunk) if word]
    if len(words) > 1:
        return words
    from_label = [w for w in re.split(r"[^a-z0-9]+", label.lower()) if w]
    return from_label or words


def derive_spellings(name: str, label: str) -> set[str]:
    """Headers that unambiguously mean a field called `name`.

    Generated rather than demanded of whoever builds the schema, because a header
    like `emp_id` or `joining_date` is what the client's export actually contains
    and nobody lists those up front.

    Three rules, each of which was measured against the sample files before being
    kept: the name and label themselves, the head noun alone (`workEmail` is very
    often just `email`), and every substitution of a vocabulary synonym. Rules
    that generated initialisms were tried and removed — they matched nothing the
    other three did not, while inventing collisions like `son` for a start date.

    Combinatorial over the vocabulary, but bounded: field names are a handful of
    words and each word has a handful of synonyms.
    """
    words = _split_words(name, label)
    out: set[str] = {normalize_header(name), normalize_header(label)}
    if not words:
        return {spelling for spelling in out if spelling}

    out.add(normalize_header("".join(words)))
    if len(words) > 1:
        # The head noun alone: "workEmail" is very often just "email".
        out.add(normalize_header(words[-1]))

    options = [(word, *_VOCABULARY.get(word, ())) for word in words]
    for combination in itertools.product(*options):
        out.add(normalize_header("".join(combination)))

    # One- and two-character spellings collide with too much to be safe.
    return {spelling for spelling in out if len(spelling) > 2}
