"""The target contract the migration maps onto.

`schemas/employee.target.schema.json` is the authority for validation. This
module adds the mapping metadata the engine needs — accepted header spellings
and semantic value kinds — and cross-checks its field list against the schema at
import time so the two cannot drift apart silently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

SCHEMA_PATH: Final = Path(__file__).resolve().parents[2] / "schemas" / "employee.target.schema.json"


@lru_cache(maxsize=1)
def target_schema() -> dict[str, Any]:
    """The JSON Schema that defines a valid target record."""
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema: dict[str, Any] = json.load(handle)
    return schema


class ValueKind(StrEnum):
    """Semantic shape of a value. Drives type-compatibility checks."""

    IDENTIFIER = "identifier"
    PERSON_NAME = "person_name"
    EMAIL = "email"
    DATE = "date"
    TEXT = "text"
    ENUM = "enum"


class TargetField(StrEnum):
    """Field names in the target schema."""

    EMPLOYEE_ID = "employeeId"
    FULL_NAME = "fullName"
    WORK_EMAIL = "workEmail"
    START_DATE = "startDate"
    END_DATE = "endDate"
    DEPARTMENT = "department"
    EMPLOYMENT_TYPE = "employmentType"


@dataclass(frozen=True, slots=True)
class TargetFieldSpec:
    """Everything the mapping policy needs to know about one target field."""

    name: TargetField
    label: str
    description: str
    required: bool
    kind: ValueKind
    #: Header spellings that unambiguously mean this field. Compared after
    #: normalisation, so casing, spacing and punctuation need not be listed.
    aliases: frozenset[str]
    enum_values: tuple[str, ...] = ()


TARGET_FIELDS: Final[tuple[TargetFieldSpec, ...]] = (
    TargetFieldSpec(
        name=TargetField.EMPLOYEE_ID,
        label="Employee ID",
        description="Unique workforce identifier.",
        required=True,
        kind=ValueKind.IDENTIFIER,
        aliases=frozenset(
            {
                "employeeid",
                "empid",
                "employeenumber",
                "empno",
                "employeecode",
                "empcode",
                "staffid",
                "staffnumber",
                "personnelnumber",
                "workerid",
                "id",
            }
        ),
    ),
    TargetFieldSpec(
        name=TargetField.FULL_NAME,
        label="Full name",
        description="Employee's full display name.",
        required=True,
        kind=ValueKind.PERSON_NAME,
        aliases=frozenset(
            {
                "fullname",
                "name",
                "employeename",
                "empname",
                "empnm",
                "staffname",
                "displayname",
                "legalname",
                "completename",
            }
        ),
    ),
    TargetFieldSpec(
        name=TargetField.WORK_EMAIL,
        label="Work email",
        description="Primary work email address.",
        required=True,
        kind=ValueKind.EMAIL,
        aliases=frozenset(
            {
                "workemail",
                "email",
                "emailaddress",
                "officeemail",
                "companyemail",
                "businessemail",
                "corporateemail",
                "workmail",
            }
        ),
    ),
    TargetFieldSpec(
        name=TargetField.START_DATE,
        label="Start date",
        description="Date employment began.",
        required=True,
        kind=ValueKind.DATE,
        aliases=frozenset(
            {
                "startdate",
                "joindate",
                "joiningdate",
                "dateofjoining",
                "doj",
                "hiredate",
                "datehired",
                "employmentstartdate",
                "commencementdate",
            }
        ),
    ),
    TargetFieldSpec(
        name=TargetField.END_DATE,
        label="End date",
        description="Date employment ended; empty for current employees.",
        required=False,
        kind=ValueKind.DATE,
        aliases=frozenset(
            {
                "enddate",
                "exitdate",
                "leavingdate",
                "dateofleaving",
                "dol",
                "terminationdate",
                "lastworkingday",
                "lastdate",
                "separationdate",
                "employmentenddate",
            }
        ),
    ),
    TargetFieldSpec(
        name=TargetField.DEPARTMENT,
        label="Department",
        description="Organisational unit.",
        required=False,
        kind=ValueKind.TEXT,
        aliases=frozenset(
            {
                "department",
                "dept",
                "departmentname",
                "division",
                "team",
                "businessunit",
                "function",
                "orgunit",
            }
        ),
    ),
    TargetFieldSpec(
        name=TargetField.EMPLOYMENT_TYPE,
        label="Employment type",
        description="Nature of the employment contract.",
        required=False,
        kind=ValueKind.ENUM,
        aliases=frozenset(
            {
                "employmenttype",
                "emptype",
                "employeetype",
                "contracttype",
                "workertype",
                "employmentstatus",
                "engagementtype",
            }
        ),
        enum_values=("full_time", "part_time", "contract", "intern"),
    ),
)

_FIELD_INDEX: Final[dict[str, TargetFieldSpec]] = {spec.name.value: spec for spec in TARGET_FIELDS}

REQUIRED_FIELDS: Final[tuple[TargetField, ...]] = tuple(
    spec.name for spec in TARGET_FIELDS if spec.required
)


def get_field(name: str) -> TargetFieldSpec | None:
    """Look up a field specification by target name."""
    return _FIELD_INDEX.get(name)


def is_target_field(name: str) -> bool:
    """Whether `name` is a field the target schema defines."""
    return name in _FIELD_INDEX


def _verify_against_schema() -> None:
    """Fail fast if the registry and the JSON Schema disagree.

    These two definitions have to agree for validation and mapping to describe
    the same contract, and a mismatch would otherwise show up as a confusing
    validation error much later.
    """
    schema = target_schema()
    schema_fields = set(schema["properties"])
    registry_fields = set(_FIELD_INDEX)
    if schema_fields != registry_fields:
        missing = schema_fields - registry_fields
        extra = registry_fields - schema_fields
        raise RuntimeError(
            "Target registry does not match the JSON Schema. "
            f"Missing from registry: {sorted(missing)}. Not in schema: {sorted(extra)}."
        )

    schema_required = set(schema.get("required", []))
    registry_required = {field.value for field in REQUIRED_FIELDS}
    if schema_required != registry_required:
        raise RuntimeError(
            "Required fields disagree. "
            f"Schema: {sorted(schema_required)}. Registry: {sorted(registry_required)}."
        )


_verify_against_schema()
