"""Validation against a target schema, and the two-pass repair policy.

A record is evaluated at most twice: once as mapped, and once more after a
single bounded pass of safe repairs. Failing both produces an escalation
carrying *both* error sets, so the reviewer can see what was attempted. There is
deliberately no third attempt and no model in the repair path — retrying a value
the rules cannot fix only burns budget and delays the human who must decide.

The rules beyond JSON Schema are driven by the schema's own declarations rather
than by field names: stricter email syntax applies to every EMAIL-kind field, and
date ordering to every field declaring `not_before`. A user's schema therefore
gets the same checks the built-in template does.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaError

from schemabridge.domain.cleanup import RecordValues, SourceValues, apply_safe_repairs
from schemabridge.domain.models import (
    AppliedRepair,
    ValidationError,
    ValidationPass,
    ValidationPassLabel,
)
from schemabridge.domain.rules import EMPTY_RULES, RuleSet
from schemabridge.domain.schema import TargetSchema, ValueKind

#: The schema's own "email" format check only looks for a single "@", so it
#: accepts "a@b" and "x@@y..z". A migration that lets those through produces
#: records the destination will reject, which is worse than catching it here.
#: Deliberately conservative rather than fully RFC 5322: a single @, a dotted
#: domain, no consecutive dots, no leading or trailing dot in either part.
_EMAIL_SYNTAX = re.compile(
    r"^(?!\.)(?!.*\.\.)[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+(?<!\.)"
    r"@"
    r"(?!-)(?!.*\.\.)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$"
)


@lru_cache(maxsize=32)
def _validator_for(schema_id: str, version: int, serialised: str) -> Draft202012Validator:
    """Compiled validator, cached per schema revision.

    Keyed on the serialised schema rather than the object, because a
    `TargetSchema` is not hashable and two equal schemas should share a
    validator. The id and version are part of the key so an edit cannot be served
    a stale validator — the real risk of caching this at all.
    """
    import json

    return Draft202012Validator(
        json.loads(serialised), format_checker=Draft202012Validator.FORMAT_CHECKER
    )


def _validator(schema: TargetSchema) -> Draft202012Validator:
    import json

    return _validator_for(
        schema.schema_id,
        schema.version,
        json.dumps(schema.json_schema, sort_keys=True),
    )


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    valid: bool
    errors: tuple[ValidationError, ...]


def _describe(error: JsonSchemaError) -> ValidationError:
    """Turn a schema error into something a non-technical reviewer can act on."""
    missing = None
    if error.validator == "required":
        # The message names the property; the path does not.
        missing = str(error.message).split("'")[1] if "'" in str(error.message) else None

    name = missing or (str(error.path[-1]) if error.path else None)
    keyword = str(error.validator)

    if keyword == "required":
        message = f"{missing} is required but was not supplied."
    elif keyword == "format":
        message = f"{name} is not a valid {error.validator_value}."
    elif keyword == "enum":
        message = f"{name} must be one of the permitted values."
    elif keyword == "additionalProperties":
        message = f"{error.message} is not part of the target schema."
    elif keyword == "minLength":
        message = f"{name} must not be empty."
    elif keyword == "pattern":
        message = f"{name} contains characters the target does not accept."
    else:
        message = f"{name or 'record'}: {error.message}"

    return ValidationError(field_name=name, code=keyword, message=message)


def _for_validation(values: SourceValues, schema: TargetSchema) -> dict[str, Any]:
    """Drop absent optionals so "not supplied" is distinct from "empty"."""
    required = schema.required_names
    candidate: dict[str, Any] = {}
    for name, value in values.items():
        if value is None:
            continue
        if value == "":
            # An empty required field is still an error the schema must catch;
            # an empty optional simply was not supplied.
            if name in required:
                candidate[name] = value
            continue
        candidate[name] = value
    return candidate


def validate_record(values: SourceValues, *, schema: TargetSchema) -> ValidationOutcome:
    """Validate one record against a schema plus its cross-field rules."""
    candidate = _for_validation(values, schema)
    errors = [_describe(error) for error in _validator(schema).iter_errors(candidate)]

    for spec in schema.fields:
        value = candidate.get(spec.name)

        # Stricter email syntax than the schema's format check provides.
        if (
            spec.kind is ValueKind.EMAIL
            and isinstance(value, str)
            and value
            and not _EMAIL_SYNTAX.match(value)
        ):
            errors.append(
                ValidationError(
                    field_name=spec.name,
                    code="email_syntax",
                    message=f'"{value}" is not a usable email address.',
                )
            )

        # A comparison between two properties, which JSON Schema cannot express:
        # a period cannot end before it began.
        if spec.not_before:
            earlier = candidate.get(spec.not_before)
            if isinstance(value, str) and isinstance(earlier, str) and value < earlier:
                other = schema.field(spec.not_before)
                errors.append(
                    ValidationError(
                        field_name=spec.name,
                        code="end_before_start",
                        message=(
                            f"{spec.label} {value} is before "
                            f"{other.label if other else spec.not_before} {earlier}."
                        ),
                    )
                )

    seen: set[tuple[str | None, str]] = set()
    unique: list[ValidationError] = []
    for error in errors:
        key = (error.field_name, error.code)
        if key in seen:
            continue
        seen.add(key)
        unique.append(error)

    return ValidationOutcome(valid=not unique, errors=tuple(unique))


@dataclass(frozen=True, slots=True)
class TwoPassResult:
    valid: bool
    values: RecordValues
    passes: tuple[ValidationPass, ...]
    repairs: tuple[AppliedRepair, ...]
    #: Both evaluations failed. Drives the escalation.
    failed_twice: bool
    #: Invalid, and no safe rule could address it.
    no_repair_available: bool


def run_validation_passes(
    source: SourceValues,
    *,
    schema: TargetSchema,
    rules: RuleSet = EMPTY_RULES,
    headers: Mapping[str, str] | None = None,
) -> TwoPassResult:
    """Evaluate a record at most twice, with one bounded repair pass between.

    Returns after the first pass when the record is already valid, so clean data
    is never needlessly rewritten.

    Learned rules widen what the single repair pass can fix; they do not add a pass.
    A record still fails twice or not at all, because "validated exactly twice" is a
    promise about how much the engine will retry before asking someone, and a rule
    that bought a third attempt would quietly break it.
    """
    first = validate_record(source, schema=schema)
    first_pass = ValidationPass(
        label=ValidationPassLabel.AS_MAPPED, valid=first.valid, errors=first.errors
    )

    if first.valid:
        return TwoPassResult(
            valid=True,
            values=dict(source),
            passes=(first_pass,),
            repairs=(),
            failed_twice=False,
            no_repair_available=False,
        )

    repaired = apply_safe_repairs(source, schema=schema, rules=rules, headers=headers)
    second = validate_record(repaired.values, schema=schema)
    second_pass = ValidationPass(
        label=ValidationPassLabel.AFTER_REPAIR, valid=second.valid, errors=second.errors
    )

    return TwoPassResult(
        valid=second.valid,
        values=repaired.values,
        passes=(first_pass, second_pass),
        repairs=repaired.repairs,
        failed_twice=not second.valid,
        # Distinguish "we tried and it still failed" from "there was nothing
        # safe to try" — the reviewer needs to know which.
        no_repair_available=not second.valid and not repaired.repairs,
    )
