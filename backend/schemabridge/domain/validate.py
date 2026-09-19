"""Validation against the target schema, and the two-pass repair policy.

A record is evaluated at most twice: once as mapped, and once more after a
single bounded pass of safe repairs. Failing both produces an escalation
carrying *both* error sets, so the reviewer can see what was attempted. There is
deliberately no third attempt and no model in the repair path — retrying a value
the rules cannot fix only burns budget and delays the human who must decide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaError

from schemabridge.domain.cleanup import RecordValues, apply_safe_repairs
from schemabridge.domain.models import (
    AppliedRepair,
    ValidationError,
    ValidationPass,
    ValidationPassLabel,
)
from schemabridge.domain.target import REQUIRED_FIELDS, target_schema

_REQUIRED_NAMES = frozenset(field.value for field in REQUIRED_FIELDS)

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


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    """Compiled schema validator, including format checks such as email."""
    return Draft202012Validator(target_schema(), format_checker=Draft202012Validator.FORMAT_CHECKER)


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


def _for_validation(values: RecordValues) -> dict[str, Any]:
    """Drop absent optionals so "not supplied" is distinct from "empty"."""
    candidate: dict[str, Any] = {}
    for name, value in values.items():
        if value is None:
            continue
        if value == "":
            # An empty required field is still an error the schema must catch;
            # an empty optional simply was not supplied.
            if name in _REQUIRED_NAMES:
                candidate[name] = value
            continue
        candidate[name] = value
    return candidate


def validate_employee(values: RecordValues) -> ValidationOutcome:
    """Validate one record against the schema plus cross-field rules."""
    candidate = _for_validation(values)
    errors = [_describe(error) for error in _validator().iter_errors(candidate)]

    # Stricter email syntax than the schema's format check provides.
    email = candidate.get("workEmail")
    if isinstance(email, str) and email and not _EMAIL_SYNTAX.match(email):
        errors.append(
            ValidationError(
                field_name="workEmail",
                code="email_syntax",
                message=f'"{email}" is not a usable email address.',
            )
        )

    # Cross-field rule JSON Schema cannot express: employment cannot end
    # before it began.
    start, end = candidate.get("startDate"), candidate.get("endDate")
    if isinstance(start, str) and isinstance(end, str) and end < start:
        errors.append(
            ValidationError(
                field_name="endDate",
                code="end_before_start",
                message=f"End date {end} is before start date {start}.",
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


def run_validation_passes(source: RecordValues) -> TwoPassResult:
    """Evaluate a record at most twice, with one bounded repair pass between.

    Returns after the first pass when the record is already valid, so clean data
    is never needlessly rewritten.
    """
    first = validate_employee(source)
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

    repaired = apply_safe_repairs(source)
    second = validate_employee(repaired.values)
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
