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

        candidate = MappingCandidate(column_id="f0:c1", target="tier", basis=MappingBasis.ALIAS)
        assert candidate.target == "tier"

        option = IssueOption(id="map:tier", label="Map to Tier", detail="", target="tier")
        assert option.target == "tier"

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


class TestRuleRoundTrip:
    """Rule models must survive the checkpointer as their own types.

    The failure this guards against is silent: an unlisted model comes back as a
    plain dict with only a log line, so the run keeps going and the mistake surfaces
    much later as a rule that never fires. Asserting the restored *type* is the only
    way to catch it at the point it is introduced.
    """

    def test_every_rule_model_restores_as_itself(self) -> None:
        from schemabridge.domain.rules import (
            DateOrder,
            ProposedRule,
            Rule,
            RuleKind,
            RuleOrigin,
            RuleProvenance,
            RuleScope,
        )
        from schemabridge.graph.checkpointer import build_serializer

        rule = Rule(
            rule_id="rule_abc",
            kind=RuleKind.HEADER_ALIAS,
            origin=RuleOrigin.LEARNED,
            schema_id="builtin:employee",
            header="Cost Centre Ref",
            field_name="department",
            provenance=RuleProvenance(run_id="r1", issue_id="i1", decision="department"),
            rationale="Taught by a decision.",
        )
        proposal = ProposedRule(
            proposal_id="p1", rule=rule, scope=RuleScope.COLUMN, rationale="Generalises."
        )
        serializer = build_serializer()

        for value in (rule, proposal, DateOrder.DAY_FIRST, RuleKind.VALUE_ALIAS):
            restored = serializer.loads_typed(serializer.dumps_typed(value))
            assert type(restored) is type(value), f"{value!r} degraded to {type(restored)}"
            assert restored == value

    def test_a_tuple_of_rules_restores_as_rules(self) -> None:
        """Rules reach the state as a tuple channel, which is how they must survive."""
        from schemabridge.domain.rules import Rule, RuleKind
        from schemabridge.graph.checkpointer import build_serializer

        stored = (
            Rule(
                rule_id="rule_1",
                kind=RuleKind.COLUMN_IGNORE,
                header="S.No",
                schema_id="builtin:employee",
            ),
            Rule(
                rule_id="rule_2",
                kind=RuleKind.VALUE_ALIAS,
                schema_id="builtin:employee",
                field_name="employmentType",
                value="Seasonal Temp",
                canonical="contract",
            ),
        )
        serializer = build_serializer()
        restored = serializer.loads_typed(serializer.dumps_typed(stored))
        assert all(isinstance(entry, Rule) for entry in restored)
        assert tuple(restored) == stored
