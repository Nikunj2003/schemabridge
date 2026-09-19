"""Target field names are data, not a closed vocabulary.

The target schema is chosen per run, so a field name cannot be a member of an
enum fixed at import time. These tests pin that: an arbitrary name flows through
the mapping models and survives the checkpointer, while the built-in template's
names keep working through the `TargetField` constants.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemabridge.domain.models import (
    IssueOption,
    MappingBasis,
    MappingCandidate,
    MappingDecision,
    MappingOutcome,
)
from schemabridge.domain.target import TargetField
from schemabridge.graph.checkpointer import build_serializer


def _decision(target: str | None) -> MappingDecision:
    return MappingDecision(
        column_id="f0:c0",
        target=target,
        outcome=MappingOutcome.AUTO_MAPPED,
        basis=MappingBasis.ALIAS,
    )


class TestUserDefinedNames:
    def test_a_name_outside_the_builtin_template_is_accepted(self) -> None:
        """A user's own schema can name a field anything."""
        assert _decision("costCentreRef").target == "costCentreRef"
        assert MappingCandidate(column_id="f0:c1", target="tier", basis=MappingBasis.ALIAS).target == "tier"
        assert IssueOption(id="map:tier", label="Map to Tier", detail="", target="tier").target == "tier"

    def test_an_absent_target_is_still_allowed(self) -> None:
        """A column that matches nothing has no target at all."""
        assert _decision(None).target is None

    def test_a_user_defined_name_survives_the_checkpointer(self) -> None:
        """A name the code has never seen must round-trip as itself.

        The serializer matches an exact (module, name) pair with no wildcard, and
        an unrecognised type comes back as a plain dict rather than raising — so a
        silent degradation here would surface much later as wrong view output.
        """
        decision = _decision("costCentreRef")
        serializer = build_serializer()
        restored = serializer.loads_typed(serializer.dumps_typed({"d": decision}))["d"]

        assert isinstance(restored, MappingDecision)
        assert restored.target == "costCentreRef"
        assert restored == decision


class TestBuiltinTemplateStillWorks:
    def test_a_constant_round_trips_and_compares_equal(self) -> None:
        """`TargetField` is a `StrEnum`, so it is usable wherever a name is."""
        decision = _decision(TargetField.EMPLOYEE_ID)
        assert decision.target == TargetField.EMPLOYEE_ID
        assert decision.target == "employeeId"

        serializer = build_serializer()
        restored = serializer.loads_typed(serializer.dumps_typed({"d": decision}))["d"]
        assert restored.target == TargetField.EMPLOYEE_ID

    def test_identity_comparison_no_longer_holds(self) -> None:
        """Documented deliberately: the stored value is a `str`, not the member.

        `is` comparisons against a `TargetField` are therefore wrong, which is
        what this change had to fix across the codebase.
        """
        decision = _decision(TargetField.EMPLOYEE_ID)
        assert decision.target is not TargetField.EMPLOYEE_ID


class TestNamesAreStillStrings:
    @pytest.mark.parametrize("bad", [123, 4.5, True, ["employeeId"]])
    def test_a_non_string_target_is_refused(self, bad: object) -> None:
        """Relaxing the enum must not mean accepting anything at all."""
        with pytest.raises(ValidationError):
            _decision(bad)  # type: ignore[arg-type]
