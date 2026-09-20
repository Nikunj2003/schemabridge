"""Reading and writing a target schema as a JSON or YAML spec.

The contract a client's destination expects usually already exists as a file —
an API's JSON Schema, a data dictionary, something a previous engagement wrote
down. Retyping it into a form is both slow and a chance to introduce a
discrepancy, so a spec can be handed over directly.

Three dialects are accepted, because a consultant arrives with whichever one they
have rather than the one this tool prefers:

* **Standard JSON Schema** (draft 2020-12 and friends): `properties`, `required`,
  `format`, `enum`. The common case, since it is what an API publishes.
* **This tool's own format**: a `fields` list. What `to_spec` writes, so a schema
  round-trips without loss — including the things JSON Schema cannot express,
  like which field identifies a record.
* **A bare field map**: `{"employeeId": "identifier", "startDate": "date"}`. Not
  a standard anything, but it is what someone writes when asked for "a simple
  spec", and refusing it would be pedantry.

YAML is parsed with `safe_load`, which constructs no arbitrary objects. A spec is
untrusted input — it arrives in a request body — and `yaml.load` on that would be
remote code execution.

What a spec cannot express is inferred conservatively, on the same principle as
`domain.infer`: a JSON Schema has no notion of which field identifies a record,
so one is *suggested* from an obvious identifier rather than declared. The
difference matters because a wrongly declared identity merges or splits records,
so the import says what it guessed and the builder opens on the result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import yaml

from schemabridge.domain.schema import (
    MAX_FIELDS,
    TargetFieldSpec,
    TargetSchema,
    ValueKind,
)

#: Longest spec accepted. Generous for a schema, small enough that parsing it
#: cannot be used to exhaust memory.
MAX_SPEC_BYTES = 256 * 1024


class SpecError(ValueError):
    """A spec that cannot be read, with a reason a person can act on."""


@dataclass(frozen=True, slots=True)
class ImportedSpec:
    """A schema read from a spec, and what had to be guessed to get there."""

    schema: TargetSchema
    #: Things inferred rather than stated, so the builder can say so instead of
    #: presenting a guess as though the file had declared it.
    assumptions: tuple[str, ...] = field(default_factory=tuple)


# --- Reading ---------------------------------------------------------------


def _load(text: str) -> Any:
    """Parse JSON or YAML, whichever it is.

    JSON first because it is a subset of YAML and its parser gives better errors
    on JSON input. `safe_load` never constructs arbitrary Python objects.
    """
    if len(text.encode("utf-8")) > MAX_SPEC_BYTES:
        raise SpecError(f"That spec is larger than {MAX_SPEC_BYTES // 1024}KB.")
    stripped = text.strip()
    if not stripped:
        raise SpecError("That file is empty.")

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    try:
        return yaml.safe_load(stripped)
    except yaml.YAMLError as error:
        detail = getattr(error, "problem", None)
        where = getattr(error, "problem_mark", None)
        line = f" at line {where.line + 1}" if where is not None else ""
        raise SpecError(
            f"That is not valid JSON or YAML{line}." + (f" {detail}." if detail else "")
        ) from None


#: JSON Schema `format` values that pin down a meaning our kinds distinguish.
_FORMAT_KINDS: dict[str, ValueKind] = {
    "email": ValueKind.EMAIL,
    "idn-email": ValueKind.EMAIL,
    "date": ValueKind.DATE,
    "date-time": ValueKind.DATE,
}

#: Words in a type or kind naming each of our kinds, so a spec written by hand
#: ("string", "str", "text") lands somewhere sensible.
_KIND_WORDS: dict[str, ValueKind] = {
    "identifier": ValueKind.IDENTIFIER,
    "id": ValueKind.IDENTIFIER,
    "person_name": ValueKind.PERSON_NAME,
    "name": ValueKind.PERSON_NAME,
    "email": ValueKind.EMAIL,
    "date": ValueKind.DATE,
    "datetime": ValueKind.DATE,
    "timestamp": ValueKind.DATE,
    "enum": ValueKind.ENUM,
    "text": ValueKind.TEXT,
    "string": ValueKind.TEXT,
    "str": ValueKind.TEXT,
}


#: Words in a *field name* that say what a bare "string" actually holds. A JSON
#: Schema commonly pins nothing beyond the type, so without this every field in a
#: published contract would import as free text — losing date normalisation, email
#: checking, and the identifier that makes cross-file merging possible.
#:
#: Read only when `type` and `format` say nothing more specific, and only as a
#: whole word, so "candidate" is not an identifier because it ends in "date".
_NAME_KINDS: tuple[tuple[frozenset[str], ValueKind], ...] = (
    (
        frozenset({"id", "identifier", "ref", "reference", "code", "number", "no", "tag"}),
        ValueKind.IDENTIFIER,
    ),
    (frozenset({"email", "mail"}), ValueKind.EMAIL),
    (frozenset({"date", "on", "at", "day"}), ValueKind.DATE),
    (frozenset({"name"}), ValueKind.PERSON_NAME),
)


def _kind_from_name(name: str) -> ValueKind | None:
    """What the field's own name suggests it holds, or None if nothing.

    Matched on the name's last word, which is the head noun: `customerId` is an
    id, `signedUpOn` is a date, `vendorName` is a name. A leading word would be
    the wrong end — `dateOfBirth` is still a date, but `idVerified` is not an id.
    """
    import re

    words = [
        word.lower()
        for word in re.split(r"[^A-Za-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name))
        if word
    ]
    if not words:
        return None
    head = words[-1]
    for vocabulary, kind in _NAME_KINDS:
        if head in vocabulary:
            return kind
    return None


def _kind_from(
    raw: Any,
    schema_format: Any,
    enum_values: tuple[str, ...],
    name: str = "",
    *,
    guess_from_name: bool = True,
) -> ValueKind:
    """The closest kind this tool models.

    An enum wins over everything: a closed vocabulary is the strongest statement
    a spec can make about a value. Then `format`, which is more specific than
    `type`. Then the type word itself. Numbers become TEXT rather than being
    rejected — we have no numeric kind, and refusing the whole spec over one
    quantity field would be unhelpful when TEXT carries it safely.
    """
    if enum_values:
        return ValueKind.ENUM
    if isinstance(schema_format, str) and (kind := _FORMAT_KINDS.get(schema_format.lower())):
        return kind
    if isinstance(raw, list):
        # A nullable JSON Schema type is ["string", "null"]; the meaning is the
        # non-null member.
        raw = next((entry for entry in raw if entry != "null"), "string")
    if isinstance(raw, str):
        word = raw.strip().lower().replace("-", "_")
        stated = _KIND_WORDS.get(word)
        if stated is not None and stated is not ValueKind.TEXT:
            return stated
        # A bare "string" says nothing, so fall back to what the name suggests.
        if guess_from_name and name and (from_name := _kind_from_name(name)):
            return from_name
        return stated or ValueKind.TEXT
    if guess_from_name and name and (from_name := _kind_from_name(name)):
        return from_name
    return ValueKind.TEXT


def _as_strings(value: Any) -> tuple[str, ...]:
    """Enum members as strings, dropping the null that marks it optional."""
    if not isinstance(value, list):
        return ()
    return tuple(str(entry) for entry in value if entry is not None and str(entry) != "")


def _label_from(name: str, given: Any) -> str:
    """A field's human label: what the spec says, else the name made readable."""
    if isinstance(given, str) and given.strip():
        return given.strip()
    import re

    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    spaced = " ".join(part for part in re.split(r"[^A-Za-z0-9]+", spaced) if part)
    return spaced[0].upper() + spaced[1:] if spaced else name


def _truthy(*values: Any) -> bool:
    """Whether any of several spellings of a flag is set."""
    return any(value is True for value in values)


def _field_from_property(name: str, body: Any, required: bool, order: int) -> TargetFieldSpec:
    """One field, from either a JSON Schema property or our own field entry."""
    if not isinstance(body, dict):
        # `{"employeeId": "identifier"}` — the bare-map dialect.
        kind = _kind_from(body, None, (), name)
        return TargetFieldSpec(
            name=name, label=_label_from(name, None), kind=kind, required=required
        )

    enum_values = _as_strings(body.get("enum") or body.get("enum_values"))
    # `kind` is our own vocabulary, so stating it is a deliberate choice and the
    # name must not override it — someone writing `kind: text` on a field called
    # `customerId` means text. `type` is JSON Schema's, where "string" is the only
    # word available for six different meanings, so there the name still speaks.
    kind = _kind_from(
        body.get("kind") or body.get("type"),
        body.get("format"),
        enum_values,
        name,
        guess_from_name="kind" not in body,
    )

    aliases = body.get("aliases") or body.get("spellings") or []
    value_aliases = body.get("value_aliases") or {}

    max_length = body.get("maxLength") or body.get("max_length")
    return TargetFieldSpec(
        name=name,
        label=_label_from(name, body.get("label") or body.get("title")),
        description=str(body.get("description") or "").strip(),
        # `required` may be stated per field as well as in the schema's own list.
        required=required or _truthy(body.get("required")),
        kind=kind,
        is_identity=_truthy(body.get("is_identity"), body.get("identity")),
        is_unique=_truthy(body.get("is_unique"), body.get("unique")),
        aliases=frozenset(str(alias) for alias in aliases if str(alias).strip())
        if isinstance(aliases, list)
        else frozenset(),
        enum_values=enum_values,
        value_aliases={
            str(key): str(value)
            for key, value in value_aliases.items()
            if isinstance(value_aliases, dict)
        }
        if isinstance(value_aliases, dict)
        else {},
        not_before=(str(body["not_before"]) if isinstance(body.get("not_before"), str) else None),
        max_length=int(max_length) if isinstance(max_length, int) else None,
    )


def _entries(document: dict[str, Any]) -> tuple[list[tuple[str, Any]], set[str]]:
    """The fields a spec declares, in order, plus which are required.

    Returns `(name, body)` pairs rather than a dict so declaration order is kept:
    it decides column order in the tables, and a spec's own order is the best
    guess at what its author considered important.
    """
    required_list = document.get("required")
    required = {str(name) for name in required_list} if isinstance(required_list, list) else set()

    # Our own format, and anything else listing fields.
    fields = document.get("fields") or document.get("columns")
    if isinstance(fields, list):
        entries: list[tuple[str, Any]] = []
        for entry in fields:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("id")
                if name:
                    entries.append((str(name), entry))
            elif isinstance(entry, str):
                entries.append((entry, {}))
        return entries, required
    if isinstance(fields, dict):
        return [(str(name), body) for name, body in fields.items()], required

    # JSON Schema.
    properties = document.get("properties")
    if isinstance(properties, dict):
        return [(str(name), body) for name, body in properties.items()], required

    # A bare map of field to type, which is neither but is what people write.
    ignored = {
        "$schema",
        "$id",
        "title",
        "name",
        "description",
        "type",
        "required",
        "additionalProperties",
        "version",
        "schema_id",
        "builtin",
    }
    bare = [
        (str(name), body)
        for name, body in document.items()
        if name not in ignored and isinstance(body, str | dict)
    ]
    if bare:
        return bare, required
    return [], required


def parse_spec(text: str, *, fallback_name: str = "Imported schema") -> ImportedSpec:
    """Read a JSON or YAML spec into a schema, saying what had to be guessed.

    Raises `SpecError` with a message intended for a person when the spec cannot
    be read at all.
    """
    document = _load(text)
    if not isinstance(document, dict):
        raise SpecError("A schema spec has to be an object, not a list or a bare value.")

    entries, required = _entries(document)
    if not entries:
        raise SpecError(
            'No fields found. Expected a JSON Schema with "properties", or a "fields" list.'
        )
    if len(entries) > MAX_FIELDS:
        raise SpecError(f"That spec has {len(entries)} fields; at most {MAX_FIELDS} are supported.")

    specs: list[TargetFieldSpec] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for order, (name, body) in enumerate(entries):
        try:
            candidate = _field_from_property(name, body, name in required, order)
        except ValueError:
            # A name JSON allows but a field name cannot be. Named, not dropped
            # silently: a missing column is worse than a refused import.
            skipped.append(name)
            continue
        if candidate.name in seen:
            skipped.append(name)
            continue
        seen.add(candidate.name)
        specs.append(candidate)

    if not specs:
        raise SpecError(
            "None of the fields in that spec have usable names. A field name must "
            "start with a letter and contain only letters, digits and underscores."
        )

    assumptions: list[str] = []
    if skipped:
        assumptions.append(
            f"Left out {len(skipped)} field(s) whose names cannot be used: "
            + ", ".join(sorted(skipped)[:5])
            + "."
        )

    specs, identity_note = _suggest_identity(specs)
    if identity_note:
        assumptions.append(identity_note)

    specs, unique_note = _suggest_uniqueness(specs)
    if unique_note:
        assumptions.append(unique_note)

    if not required and any(spec.required for spec in specs) is False:
        assumptions.append(
            "The spec marks nothing as required, so no field will block a migration."
        )

    name = document.get("name") or document.get("title") or fallback_name
    return ImportedSpec(
        schema=TargetSchema(
            schema_id="imported",
            name=str(name).strip() or fallback_name,
            description=str(document.get("description") or "").strip(),
            fields=tuple(specs),
        ),
        assumptions=tuple(assumptions),
    )


def _suggest_identity(specs: list[TargetFieldSpec]) -> tuple[list[TargetFieldSpec], str | None]:
    """Mark an identity field when the spec did not, if one is obvious.

    JSON Schema cannot say which field identifies a record, so without this every
    import would merge nothing and a two-file migration would produce duplicate
    records. Only a *required* identifier qualifies: guessing from an optional or
    free-text field risks merging two records that are not the same.
    """
    if any(spec.is_identity for spec in specs):
        return specs, None

    for index, spec in enumerate(specs):
        if spec.kind is ValueKind.IDENTIFIER and spec.required:
            updated = list(specs)
            updated[index] = spec.model_copy(update={"is_identity": True})
            return updated, (
                f"Treating {spec.label} as the field that identifies a record, since "
                f"the spec does not say. Change it in the builder if that is wrong."
            )
    return specs, (
        "No field identifies a record, so rows from different files will never be "
        "merged. Mark one in the builder if they should be."
    )


def _suggest_uniqueness(specs: list[TargetFieldSpec]) -> tuple[list[TargetFieldSpec], str | None]:
    """Flag a required email as unique, which is nearly always the intent.

    Non-blocking either way — a duplicate is raised for a person to look at, never
    acted on — so the cost of guessing wrong is one question, not a wrong
    migration.
    """
    if any(spec.is_unique for spec in specs):
        return specs, None
    for index, spec in enumerate(specs):
        if spec.kind is ValueKind.EMAIL and spec.required:
            updated = list(specs)
            updated[index] = spec.model_copy(update={"is_unique": True})
            return updated, (
                f"Two records sharing a {spec.label} will be flagged for you to check."
            )
    return specs, None


# --- Writing ---------------------------------------------------------------


def to_spec(schema: TargetSchema) -> dict[str, Any]:
    """A schema as a spec, in this tool's own format.

    Its own format rather than JSON Schema, because JSON Schema cannot express
    which field identifies a record, which must be unique, or the accepted
    spellings of an enum value — and a round trip that quietly dropped those
    would be worse than no export at all. `parse_spec` reads it back exactly.

    Derived header spellings are deliberately omitted: they are generated from the
    name and label, so writing them would freeze today's derivation into the file
    and stop an improvement to it from reaching an imported schema.
    """
    fields: list[dict[str, Any]] = []
    for spec in schema.fields:
        entry: dict[str, Any] = {
            "name": spec.name,
            "label": spec.label,
            "kind": spec.kind.value,
            "required": spec.required,
        }
        if spec.description:
            entry["description"] = spec.description
        if spec.is_identity:
            entry["is_identity"] = True
        if spec.is_unique:
            entry["is_unique"] = True
        if spec.enum_values:
            entry["enum_values"] = list(spec.enum_values)
        if spec.value_aliases:
            entry["value_aliases"] = dict(spec.value_aliases)
        if spec.not_before:
            entry["not_before"] = spec.not_before
        if spec.aliases:
            entry["aliases"] = sorted(spec.aliases)
        if spec.max_length is not None:
            entry["max_length"] = spec.max_length
        fields.append(entry)

    document: dict[str, Any] = {"name": schema.name}
    if schema.description:
        document["description"] = schema.description
    document["fields"] = fields
    return document


def to_yaml(schema: TargetSchema) -> str:
    """A schema as YAML, which is what people hand to each other."""
    written: str = yaml.safe_dump(to_spec(schema), sort_keys=False, allow_unicode=True)
    return written
