"""The rule overlay, and the guarantee that an empty one changes nothing.

The first test in this file is the most important one in the feature. Everything
else the rules layer does is additive; this asserts the subtraction — that a
session with no rules gets byte-for-byte the decisions the engine made before the
overlay existed. Without it, "we added learned rules" and "we changed how every
migration maps" are indistinguishable.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemabridge.domain.rules import (
    EMPTY_RULES,
    DateOrder,
    Rule,
    RuleKind,
    RuleOrigin,
    RuleRejectedError,
    RuleSet,
    builtin_rules,
    check_against_schema,
)
from schemabridge.domain.target import BUILTIN_SCHEMA

SCHEMA_ID = BUILTIN_SCHEMA.schema_id


def _rule(kind: RuleKind, **fields: object) -> Rule:
    fields.setdefault("schema_id", SCHEMA_ID)
    return Rule(kind=kind, **fields)  # type: ignore[arg-type]


def _alias(header: str, field_name: str, *, rule_id: str = "r1", **extra: object) -> Rule:
    return _rule(
        RuleKind.HEADER_ALIAS, rule_id=rule_id, header=header, field_name=field_name, **extra
    )


def _set(*rules: Rule, schema_id: str = SCHEMA_ID) -> RuleSet:
    return RuleSet(rules, schema_id=schema_id)


class TestEmptyRuleSet:
    def test_empty_set_is_falsy_and_answers_nothing(self) -> None:
        assert not EMPTY_RULES
        assert EMPTY_RULES.alias_for("Cost Centre Ref") is None
        assert EMPTY_RULES.canonical_for("employmentType", "Permanent") is None
        assert EMPTY_RULES.date_order_for(header="doj") is None
        assert EMPTY_RULES.ignores("S.No") is None
        assert EMPTY_RULES.hits == {}

    def test_a_set_of_disabled_rules_is_also_empty(self) -> None:
        """Disabling is not the same as deleting, and must behave as absence."""
        rules = _set(_alias("Cost Centre Ref", "department", enabled=False))
        assert not rules
        assert rules.alias_for("Cost Centre Ref") is None


class TestMatching:
    def test_header_match_is_normalised_on_both_sides(self) -> None:
        rules = _set(_alias("Cost Centre Ref", "department"))
        for spelling in ("Cost Centre Ref", "cost_centre_ref", "COST.CENTRE.REF", " ref "):
            expected = "department" if spelling.strip().lower() != "ref" else None
            found = rules.alias_for(spelling)
            if expected is None:
                assert found is None, spelling
            else:
                assert found is not None, spelling
                assert found.field_name == expected

    def test_a_near_miss_does_not_match(self) -> None:
        """Matching is exact after normalisation, never fuzzy."""
        rules = _set(_alias("Cost Centre Ref", "department"))
        assert rules.alias_for("Cost Centre") is None
        assert rules.alias_for("Cost Centre Reference") is None

    def test_value_alias_is_scoped_to_its_field(self) -> None:
        rules = _set(
            _rule(
                RuleKind.VALUE_ALIAS,
                rule_id="v1",
                field_name="employmentType",
                value="Seasonal Temp",
                canonical="contract",
            )
        )
        found = rules.canonical_for("employmentType", "seasonal temp")
        assert found is not None
        assert found.canonical == "contract"
        # The same spelling under a different field is a different question.
        assert rules.canonical_for("department", "Seasonal Temp") is None

    def test_column_specific_date_order_beats_field_wide(self) -> None:
        """One export writing day-first does not make every source do so."""
        rules = _set(
            _rule(
                RuleKind.DATE_ORDER,
                rule_id="wide",
                field_name="startDate",
                date_order=DateOrder.MONTH_FIRST,
            ),
            _rule(
                RuleKind.DATE_ORDER,
                rule_id="narrow",
                header="doj",
                date_order=DateOrder.DAY_FIRST,
            ),
        )
        narrow = rules.date_order_for(header="doj", field_name="startDate")
        assert narrow is not None
        assert narrow.date_order is DateOrder.DAY_FIRST

        wide = rules.date_order_for(header="Joining Date", field_name="startDate")
        assert wide is not None
        assert wide.date_order is DateOrder.MONTH_FIRST


class TestLayering:
    def test_a_later_layer_wins_for_the_same_header(self) -> None:
        """Callers pass layers in precedence order, lowest first."""
        rules = _set(
            _alias("Cost Centre Ref", "department", rule_id="builtin", origin=RuleOrigin.BUILTIN),
            _alias("Cost Centre Ref", "employmentType", rule_id="mine"),
        )
        found = rules.alias_for("Cost Centre Ref")
        assert found is not None
        assert found.rule_id == "mine"

    def test_an_override_disables_the_rule_it_names(self) -> None:
        rules = _set(
            _alias("Division", "department", rule_id="builtin:header_alias:department:division"),
            _rule(
                RuleKind.OVERRIDE,
                rule_id="o1",
                origin=RuleOrigin.OVERRIDE,
                targets_rule_id="builtin:header_alias:department:division",
            ),
        )
        assert rules.alias_for("Division") is None

    def test_a_disabled_override_restores_the_rule(self) -> None:
        """Turning an override off must not leave the original still disabled."""
        rules = _set(
            _alias("Division", "department", rule_id="b1"),
            _rule(RuleKind.OVERRIDE, rule_id="o1", targets_rule_id="b1", enabled=False),
        )
        assert rules.alias_for("Division") is not None

    def test_a_rule_for_another_schema_is_not_in_force(self) -> None:
        """The whole point of tying a rule to a schema: it cannot leak sideways."""
        rules = RuleSet(
            (_alias("Ref", "department", rule_id="elsewhere", schema_id="sch_other"),),
            schema_id=SCHEMA_ID,
        )
        assert rules.alias_for("Ref") is None
        assert not rules

    def test_a_rule_for_this_schema_is_in_force(self) -> None:
        rules = _set(_alias("Ref", "department", rule_id="here"))
        assert rules.alias_for("Ref") is not None


class TestHitCounting:
    def test_hits_accumulate_per_rule(self) -> None:
        rules = _set(_alias("Cost Centre Ref", "department", rule_id="r9"))
        rules.alias_for("Cost Centre Ref")
        rules.alias_for("cost_centre_ref")
        rules.alias_for("Something Else")
        assert rules.hits == {"r9": 2}

    def test_a_miss_records_nothing(self) -> None:
        rules = _set(_alias("Cost Centre Ref", "department"))
        rules.alias_for("Unrelated")
        assert rules.hits == {}


class TestShapeValidation:
    """A rule missing what its consumer needs is refused, not stored inert."""

    @pytest.mark.parametrize(
        ("kind", "payload"),
        [
            (RuleKind.HEADER_ALIAS, {"header": "ref"}),
            (RuleKind.HEADER_ALIAS, {"field_name": "department"}),
            (RuleKind.VALUE_ALIAS, {"field_name": "employmentType", "value": "temp"}),
            (RuleKind.VALUE_ALIAS, {"field_name": "employmentType", "canonical": "contract"}),
            (RuleKind.DATE_ORDER, {"header": "doj"}),
            (RuleKind.DATE_ORDER, {"date_order": DateOrder.DAY_FIRST}),
            (RuleKind.COLUMN_IGNORE, {}),
            (RuleKind.OVERRIDE, {}),
        ],
    )
    def test_incomplete_rules_are_refused(self, kind: RuleKind, payload: dict[str, object]) -> None:
        with pytest.raises(ValidationError):
            _rule(kind, **payload)

    @pytest.mark.parametrize(
        ("kind", "payload"),
        [
            (RuleKind.HEADER_ALIAS, {"header": "ref", "field_name": "department"}),
            (RuleKind.COLUMN_IGNORE, {"header": "sno"}),
            (RuleKind.OVERRIDE, {"targets_rule_id": "builtin:x"}),
        ],
    )
    def test_every_kind_needs_a_schema(self, kind: RuleKind, payload: dict[str, object]) -> None:
        """A rule that applied everywhere would make the rules page unanswerable."""
        with pytest.raises(ValidationError, match="schema"):
            Rule(kind=kind, schema_id="", **payload)  # type: ignore[arg-type]

    def test_unknown_fields_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            Rule(
                kind=RuleKind.HEADER_ALIAS,
                schema_id=SCHEMA_ID,
                header="ref",
                field_name="department",
                pattern="^ref.*$",  # type: ignore[call-arg]
            )

    def test_a_rule_carries_no_expression_field(self) -> None:
        """The absence of a regex or predicate field is a deliberate guarantee."""
        forbidden = {"pattern", "regex", "expression", "predicate", "script", "code"}
        assert forbidden.isdisjoint(Rule.model_fields)

    def test_rationale_is_capped(self) -> None:
        rule = _alias("Ref", "department", rationale="x" * 500)
        assert len(rule.rationale) <= 240


class TestSchemaVerification:
    """One gate, applied to a hand-written rule and a drafted one alike.

    These live here rather than only in `test_induce.py` because the function is
    shared on purpose: if hand-writing were checked less strictly than drafting, the
    manual path would be the dangerous one.
    """

    def test_an_ambiguous_header_is_refused(self) -> None:
        """The refusal that matters most.

        "Date" is claimed by both startDate and endDate, which is what makes a bare
        Date column escalate. A rule resolving it would remove that escalation for
        every future run, and every row in those files would be silently misdated.
        """
        for header in ("Date", "dates", "Effective Date", "Contract Date"):
            rule = _alias(header, "startDate")
            with pytest.raises(RuleRejectedError, match="could be"):
                check_against_schema(rule, BUILTIN_SCHEMA)

    def test_an_unambiguous_header_is_allowed(self) -> None:
        """The refusal is targeted, not a blanket ban on header rules."""
        check_against_schema(_alias("Cost Centre Ref", "department"), BUILTIN_SCHEMA)

    def test_an_unknown_field_is_refused(self) -> None:
        with pytest.raises(RuleRejectedError, match="not a field"):
            check_against_schema(_alias("Ref", "notAField"), BUILTIN_SCHEMA)

    def test_a_value_outside_the_vocabulary_is_refused(self) -> None:
        rule = _rule(
            RuleKind.VALUE_ALIAS,
            field_name="employmentType",
            value="Seasonal Temp",
            canonical="seasonal",
        )
        with pytest.raises(RuleRejectedError, match="permits"):
            check_against_schema(rule, BUILTIN_SCHEMA)

    def test_a_value_inside_the_vocabulary_is_allowed(self) -> None:
        rule = _rule(
            RuleKind.VALUE_ALIAS,
            field_name="employmentType",
            value="Seasonal Temp",
            canonical="contract",
        )
        check_against_schema(rule, BUILTIN_SCHEMA)

    def test_a_value_rule_on_a_non_enum_field_is_refused(self) -> None:
        rule = _rule(RuleKind.VALUE_ALIAS, field_name="fullName", value="priya", canonical="Priya")
        with pytest.raises(RuleRejectedError, match="fixed set"):
            check_against_schema(rule, BUILTIN_SCHEMA)

    def test_a_date_rule_on_a_non_date_field_is_refused(self) -> None:
        rule = _rule(RuleKind.DATE_ORDER, field_name="department", date_order=DateOrder.DAY_FIRST)
        with pytest.raises(RuleRejectedError, match="does not hold dates"):
            check_against_schema(rule, BUILTIN_SCHEMA)

    def test_an_ignore_rule_needs_no_field_and_is_allowed(self) -> None:
        """An ignored column is a fact about the source, not about the contract."""
        check_against_schema(_rule(RuleKind.COLUMN_IGNORE, header="S.No"), BUILTIN_SCHEMA)


class TestBuiltinProjection:
    def test_no_builtin_rule_claims_an_ambiguous_header(self) -> None:
        """Otherwise turning one off would be how a person breaks their own runs."""
        shared = {
            header for header, names in BUILTIN_SCHEMA.spelling_index.items() if len(names) > 1
        }
        assert shared, "the fixture schema should have at least one ambiguous header"
        claimed = {
            rule.header
            for rule in builtin_rules(BUILTIN_SCHEMA)
            if rule.kind is RuleKind.HEADER_ALIAS
        }
        assert shared.isdisjoint(claimed)

    def test_builtin_rules_name_their_schema(self) -> None:
        assert all(
            rule.schema_id == BUILTIN_SCHEMA.schema_id for rule in builtin_rules(BUILTIN_SCHEMA)
        )

    def test_builtin_rules_are_marked_as_shipped(self) -> None:
        assert all(rule.origin is RuleOrigin.BUILTIN for rule in builtin_rules(BUILTIN_SCHEMA))

    def test_every_builtin_rule_passes_its_own_verification(self) -> None:
        """The shipped layer must satisfy the bar it holds everyone else to."""
        for rule in builtin_rules(BUILTIN_SCHEMA):
            check_against_schema(rule, BUILTIN_SCHEMA)
