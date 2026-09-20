"""The built-in target template.

One schema, shipped so the tool does something useful on first run and so the
demo has a known shape. It is *a* value of `TargetSchema`, not a privileged one:
a user can copy it, edit every field, or define something unrelated to employment
entirely, and the engine treats all of those identically.

Two things here are deliberate rather than leftover:

* **The curated aliases stay**, even though `derive_spellings` generates most of
  them. Derivation alone matches 9 of the 13 headers in the sample files; the
  curated list closes `emp_nm`, `doj` and `emp_type`. Keeping both means the
  shipped template's behaviour is exactly what it was before schemas became data.
* **`TargetField` stays a `StrEnum`.** It is no longer a type constraint — field
  names are plain strings now — but it names this template's fields for the code
  and tests that legitimately talk about the shipped shape, and it is a `str`
  subclass so `decision.target == TargetField.EMPLOYEE_ID` still holds. It also
  remains in the checkpointer's allowlist so runs created before the change
  deserialise.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from schemabridge.domain.schema import (
    TargetFieldSpec,
    TargetSchema,
    ValueKind,
)

__all__ = [
    "BUILTIN_SCHEMA",
    "BUILTIN_SCHEMA_ID",
    "REQUIRED_FIELDS",
    "TARGET_FIELDS",
    "TargetField",
    "TargetFieldSpec",
    "TargetSchema",
    "ValueKind",
    "get_field",
    "is_target_field",
    "target_schema",
]

#: Stable id, so a run that pinned the built-in template can be recognised as
#: having used it rather than a user's copy.
BUILTIN_SCHEMA_ID: Final = "builtin:employee"


class TargetField(StrEnum):
    """Field names in the built-in template.

    Not a constraint on what a schema may contain — see the module docstring.
    """

    EMPLOYEE_ID = "employeeId"
    FULL_NAME = "fullName"
    WORK_EMAIL = "workEmail"
    START_DATE = "startDate"
    END_DATE = "endDate"
    DEPARTMENT = "department"
    EMPLOYMENT_TYPE = "employmentType"


#: Spellings for each permitted employment type. Explicit by design: an unlisted
#: spelling escalates rather than being fuzzy-matched, because deciding that
#: "Seasonal Temp" means "contract" is a business call, not a formatting one.
_EMPLOYMENT_TYPE_ALIASES: Final[dict[str, str]] = {
    "fulltime": "full_time",
    "full": "full_time",
    "permanent": "full_time",
    "fte": "full_time",
    "regular": "full_time",
    "parttime": "part_time",
    "part": "part_time",
    "contract": "contract",
    "contractor": "contract",
    "contractual": "contract",
    "temporary": "contract",
    "temp": "contract",
    "fixedterm": "contract",
    "intern": "intern",
    "internship": "intern",
    "trainee": "intern",
    "apprentice": "intern",
}


BUILTIN_SCHEMA: Final = TargetSchema(
    schema_id=BUILTIN_SCHEMA_ID,
    name="Employee",
    description="Target contract for a migrated employee record.",
    builtin=True,
    fields=(
        TargetFieldSpec(
            name=TargetField.EMPLOYEE_ID,
            label="Employee ID",
            description=(
                "Unique workforce identifier. Treated as an opaque string so leading "
                "zeros and prefixes survive migration."
            ),
            required=True,
            kind=ValueKind.IDENTIFIER,
            # The field rows are keyed on: two files describing the same id are
            # the same person, which is what makes cross-file merging possible.
            is_identity=True,
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
            description="Employee's full display name as recorded by the client.",
            required=True,
            kind=ValueKind.PERSON_NAME,
            max_length=200,
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
            # One address under two ids is either a duplicate person or a typo,
            # and the schema cannot say which.
            is_unique=True,
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
            description="Date employment began, as a calendar date.",
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
                    # Shared with the end date on purpose: a column called
                    # "Effective Date" could be either, so listing it on both
                    # makes the spelling index report it as ambiguous and the
                    # reviewer gets asked. See TargetSchema.spelling_index.
                    "dates",
                    "employmentdate",
                    "effectivedate",
                    "contractdate",
                }
            ),
        ),
        TargetFieldSpec(
            name=TargetField.END_DATE,
            label="End date",
            description=(
                "Date employment ended. Null for current employees. Must not "
                "precede the start date."
            ),
            required=False,
            kind=ValueKind.DATE,
            # Employment cannot end before it began. JSON Schema cannot express a
            # comparison between two properties, so validation checks it.
            not_before=TargetField.START_DATE,
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
                    # The other half of the shared-spelling pair above.
                    "dates",
                    "employmentdate",
                    "effectivedate",
                    "contractdate",
                }
            ),
        ),
        TargetFieldSpec(
            name=TargetField.DEPARTMENT,
            label="Department",
            description="Organisational unit the employee belongs to.",
            required=False,
            kind=ValueKind.TEXT,
            max_length=120,
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
            enum_values=("full_time", "part_time", "contract", "intern"),
            value_aliases=_EMPLOYMENT_TYPE_ALIASES,
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
        ),
    ),
)


# --- Compatibility surface -------------------------------------------------
#
# These read the built-in template. Code that must work on a user's schema takes
# a `TargetSchema` argument instead; these exist for the places that genuinely
# mean the shipped shape — the default for a new run, and the tests that pin its
# behaviour.

TARGET_FIELDS: Final[tuple[TargetFieldSpec, ...]] = BUILTIN_SCHEMA.fields

REQUIRED_FIELDS: Final[tuple[str, ...]] = tuple(sorted(BUILTIN_SCHEMA.required_names))


def target_schema() -> dict[str, Any]:
    """The built-in template's JSON Schema, generated from its fields."""
    return BUILTIN_SCHEMA.json_schema


def get_field(name: str) -> TargetFieldSpec | None:
    """Look up a field in the built-in template."""
    return BUILTIN_SCHEMA.field(name)


def is_target_field(name: str) -> bool:
    """Whether the built-in template defines `name`."""
    return BUILTIN_SCHEMA.has(name)
